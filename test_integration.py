"""Integration checks for the Smart Retail frontend/API/data/model pipeline."""

from pathlib import Path
import sys

import joblib
import requests
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parent
MONGODB_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "smart_retail_db"
API_BASE_URL = "http://localhost:8000"
FRONTEND_ORIGIN = "http://localhost:3000"
REQUEST_TIMEOUT_SECONDS = 5

PAYLOAD = {
    "store_id": "STORE_01",
    "product_id": "PROD_01",
    "price": 49.99,
    "discount": 0.10,
    "units_ordered": 50,
    "weather_condition": "Clear",
    "seasonality": "None",
}


def check_mongodb() -> bool:
    """Verify that the configured MongoDB instance accepts a ping."""
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=REQUEST_TIMEOUT_SECONDS * 1000)
    try:
        client.admin.command("ping")
        client[DATABASE_NAME].name
        print(f"[PASS] MongoDB Connection Status: connected to {DATABASE_NAME}")
        return True
    except Exception as exc:
        print(f"[FAIL] MongoDB Connection Status: could not reach {MONGODB_URI}: {exc}")
        return False
    finally:
        client.close()


def check_model_artifact() -> bool:
    """Verify that the trained model artifact exists and can be deserialized."""
    model_path = PROJECT_ROOT / "model.pkl"
    try:
        if not model_path.is_file():
            raise FileNotFoundError(f"artifact not found at {model_path}")
        model = joblib.load(model_path)
        if model is None:
            raise ValueError("joblib returned a null model")
        print(f"[PASS] XGBoost 'model.pkl' Artifact Load Status: loaded {type(model).__name__}")
        return True
    except Exception as exc:
        print(f"[FAIL] XGBoost 'model.pkl' Artifact Load Status: {exc}")
        return False


def check_frontend() -> bool:
    """Verify that the dashboard is reachable from the configured frontend origin."""
    try:
        response = requests.get(FRONTEND_ORIGIN, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 200:
            raise AssertionError(f"dashboard returned HTTP {response.status_code}")
        if "<html" not in response.text.lower():
            raise AssertionError("dashboard response does not contain an HTML document")
        print(f"[PASS] Frontend Dashboard Connection Status: {FRONTEND_ORIGIN} is reachable")
        return True
    except requests.RequestException as exc:
        print(
            f"[FAIL] Frontend dashboard connection: {exc}. "
            "Start the dashboard with 'python -m http.server 3000 --directory frontend' and retry."
        )
        return False
    except AssertionError as exc:
        print(f"[FAIL] Frontend dashboard response validation: {exc}")
        return False


def check_api() -> bool:
    """Validate health, CORS, and prediction behavior exposed by FastAPI."""
    headers = {"Origin": FRONTEND_ORIGIN}
    try:
        health_response = requests.get(
            f"{API_BASE_URL}/health",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if health_response.status_code != 200:
            raise AssertionError(
                f"health endpoint returned HTTP {health_response.status_code}: "
                f"{health_response.text}"
            )
        if health_response.json() != {"status": "healthy"}:
            raise AssertionError(f"unexpected health JSON: {health_response.json()}")
        if health_response.headers.get("access-control-allow-origin") != FRONTEND_ORIGIN:
            raise AssertionError("health response did not allow Origin http://localhost:3000")
        print("[PASS] FastAPI Server Ping Status: HTTP 200 and healthy")

        prediction_response = requests.post(
            f"{API_BASE_URL}/predict",
            json=PAYLOAD,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if prediction_response.status_code != 200:
            raise AssertionError(
                f"predict endpoint returned HTTP {prediction_response.status_code}: "
                f"{prediction_response.text}"
            )
        if prediction_response.headers.get("access-control-allow-origin") != FRONTEND_ORIGIN:
            raise AssertionError("prediction response did not allow Origin http://localhost:3000")

        response_json = prediction_response.json()
        predicted_demand = response_json.get("predicted_demand")
        if isinstance(predicted_demand, bool) or not isinstance(predicted_demand, (int, float)):
            raise AssertionError(f"predicted_demand is not numerical: {predicted_demand!r}")
        if predicted_demand <= 0:
            raise AssertionError(f"predicted_demand must be positive: {predicted_demand}")

        print(
            "[PASS] Prediction Response Validation: "
            f"inputs={PAYLOAD} -> predicted_demand={predicted_demand}"
        )
        return True
    except requests.RequestException as exc:
        print(
            f"[FAIL] FastAPI connection: {exc}. "
            "Start the backend at http://localhost:8000 and retry."
        )
        return False
    except (AssertionError, ValueError) as exc:
        print(f"[FAIL] FastAPI response validation: {exc}")
        return False


def main() -> int:
    print("Smart Retail Integration Test")
    print("=" * 32)
    checks_passed = [check_mongodb(), check_model_artifact(), check_frontend(), check_api()]
    print("=" * 32)
    if all(checks_passed):
        print("[PASS] Complete connection pipeline validated.")
        return 0
    print("[FAIL] Integration pipeline validation failed. Review the diagnostics above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())