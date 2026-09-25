from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from pydantic import BaseModel, Field
from xgboost import XGBRegressor

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

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("frontend/index.html")

# Global configuration & state
MODEL_PATH = os.getenv("MODEL_PATH", "model.json")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "smart_retail_db")
model = None
mongo_client = None


class PredictionRequest(BaseModel):
    store_id: str = Field(..., example="STORE_01")
    product_id: str = Field(..., example="PROD_01")
    price: float = Field(..., gt=0, example=49.99)
    discount: float = Field(..., ge=0, le=1.0, example=0.10)
    units_ordered: int = Field(default=50, ge=0, example=50)
    weather_condition: str = Field(default="Clear", example="Clear")
    seasonality: str = Field(default="None", example="None")


@app.on_event("startup")
def load_model_artifact():
    """Loads the model artifact and initializes the MongoDB client upon startup."""
    global model, mongo_client

    # 1. Load ML Model
    try:
        model = XGBRegressor(enable_categorical=True)
        model.load_model(MODEL_PATH)
        logger.info(f"Successfully loaded model artifact from '{MODEL_PATH}'.")
    except Exception as e:
        logger.error(f"Failed to load model artifact '{MODEL_PATH}': {str(e)}")
        model = None

    # 2. Connect to MongoDB
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        mongo_client.admin.command("ping")
        logger.info("Connected to MongoDB database '%s'.", MONGODB_DATABASE)
    except Exception as e:
        logger.warning("MongoDB unavailable: %s", e)
        mongo_client = None

@app.on_event("shutdown")
def close_database_clients():
    if mongo_client:
        mongo_client.close()


def log_prediction(payload: PredictionRequest, predicted_demand, status: str):
    if mongo_client is None:
        return
    try:
        mongo_client[MONGODB_DATABASE]["predictions"].insert_one({
            "timestamp": datetime.now(timezone.utc),
            "payload": payload.model_dump(),
            "predicted_demand": predicted_demand,
            "status": status,
        })
    except Exception as e:
        logger.error("Failed to log prediction to MongoDB: %s", e)


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
        raise HTTPException(status_code=500, detail="Model artifact 'model.json' is not loaded on the server.")

    try:
        # Keep inference columns aligned with the training pipeline.
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
        }
        
        input_df = pd.DataFrame([raw_data])

        # Cast string objects to categorical types for XGBoost compatibility
        input_df["weather_condition"] = pd.Categorical(
            input_df["weather_condition"], categories=["Clear", "Cloudy", "Rainy", "Snowy", "Sunny"]
        )
        input_df["seasonality"] = pd.Categorical(
            input_df["seasonality"], categories=["None", "Spring", "Summer", "Autumn", "Fall", "Winter"]
        )

        # Execute prediction
        prediction_value = model.predict(input_df)[0]
        predicted_demand = round(max(0.0, float(prediction_value)), 2)
        log_prediction(payload, predicted_demand, "success")

        return {
            "status": "success",
            "store_id": payload.store_id,
            "product_id": payload.product_id,
            "predicted_demand": predicted_demand
        }

    except Exception as e:
        logger.error(f"Prediction failure: {str(e)}")
        try:
            log_prediction(payload, None, "failed")
        except Exception as log_error:
            logger.error("Failed to persist prediction failure: %s", log_error)
        raise HTTPException(
            status_code=500, 
            detail=f"Inference error during model execution: {str(e)}"
        )

