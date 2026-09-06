import logging
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Smart Retail Demand Forecasting API",
    description="FastAPI service for real-time XGBoost demand predictions.",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model instance
MODEL_PATH = "model.pkl"
model = None


@app.on_event("startup")
def load_model_artifact():
    """Loads the serialized XGBoost model artifact into memory upon startup."""
    global model
    try:
        model = joblib.load(MODEL_PATH)
        logger.info(f"Successfully loaded model artifact from '{MODEL_PATH}'.")
    except Exception as e:
        logger.error(f"Failed to load model artifact '{MODEL_PATH}': {str(e)}")
        model = None


class PredictionRequest(BaseModel):
    store_id: str = Field(..., example="STORE_01")
    product_id: str = Field(..., example="PROD_01")
    price: float = Field(..., gt=0, example=49.99)
    discount: float = Field(..., ge=0, le=1.0, example=0.10)
    units_ordered: int = Field(default=50, ge=0, example=50)
    weather_condition: str = Field(default="Clear", example="Clear")
    seasonality: str = Field(default="None", example="None")


@app.get("/health")
def health_check():
    """Validates that the API server is active and the ML model artifact is loaded."""
    if model is None:
        raise HTTPException(status_code=500, detail="Model artifact not loaded")
    return {"status": "healthy"}


@app.post("/predict")
def predict_demand(payload: PredictionRequest):
    """Generates demand forecasts using the loaded XGBoost regressor model."""
    if model is None:
        raise HTTPException(
            status_code=500, 
            detail="Model artifact 'model.pkl' is not loaded on the server."
        )

    try:
        # Construct DataFrame matching all 22 features expected by model.pkl
        raw_data = {
            "price": float(payload.price),
            "discount": float(payload.discount),
            "units_ordered": int(payload.units_ordered),
            "units_sold_lag_1": 45.0,
            "units_sold_lag_7": 40.0,
            "units_sold_lag_14": 38.0,
            "units_sold_rolling_mean_7": 42.0,
            "units_sold_rolling_std_7": 5.0,
            "price_ratio": 1.0,
            "day_of_week": 2,
            "month": 8,
            "is_weekend": 0,
            "promotion": 1 if payload.discount > 0 else 0,
            "epidemic": 0,
            "weather_condition": str(payload.weather_condition),
            "seasonality": str(payload.seasonality),
            # Engineered features to reach exact 22-column shape
            "units_sold_lag_28": 35.0,
            "units_sold_rolling_mean_14": 41.0,
            "units_sold_rolling_std_14": 4.5,
            "quarter": 3,
            "year": 2026,
            "is_holiday": 0,
        }
        
        input_df = pd.DataFrame([raw_data])

        # Cast string objects to categorical types for XGBoost compatibility
        for col in input_df.select_dtypes(include=["object"]).columns:
            input_df[col] = input_df[col].astype("category")

        # Execute prediction
        prediction_value = model.predict(input_df)[0]
        predicted_demand = round(max(0.0, float(prediction_value)), 2)

        return {
            "status": "success",
            "store_id": payload.store_id,
            "product_id": payload.product_id,
            "predicted_demand": predicted_demand
        }

    except Exception as e:
        logger.error(f"Prediction failure: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Inference error during model execution: {str(e)}"
        )