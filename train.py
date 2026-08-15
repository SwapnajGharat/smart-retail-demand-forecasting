import logging
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from pymongo import MongoClient
from sklearn.metrics import mean_absolute_error, mean_squared_error

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger(__name__)


def load_collection_to_df(client: MongoClient, db_name: str, coll_name: str) -> pd.DataFrame:
    LOG.info("Loading collection %s.%s", db_name, coll_name)
    coll = client[db_name][coll_name]
    docs = list(coll.find({}, {"_id": 0}))
    if not docs:
        LOG.warning("Collection %s.%s is empty", db_name, coll_name)
        return pd.DataFrame()
    return pd.DataFrame(docs)


def prepare_data(trans_df: pd.DataFrame, ext_df: pd.DataFrame) -> pd.DataFrame:
    # Merge sales transactions with external factors
    if not ext_df.empty and "store_id" in ext_df.columns and "date" in ext_df.columns:
        df = pd.merge(trans_df, ext_df, on=["store_id", "date"], how="left")
    else:
        df = trans_df.copy()

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["store_id", "product_id", "date"]).reset_index(drop=True)

    # Calculate Lags and Rolling statistics safely without index mismatch
    df["units_sold_lag_1"] = df.groupby(["store_id", "product_id"])["units_sold"].shift(1)
    df["units_sold_lag_7"] = df.groupby(["store_id", "product_id"])["units_sold"].shift(7)
    df["units_sold_lag_14"] = df.groupby(["store_id", "product_id"])["units_sold"].shift(14)

    # Shift by 1 first to avoid data leakage before computing rolling metrics
    shifted = df.groupby(["store_id", "product_id"])["units_sold"].shift(1)
    df["units_sold_rolling_mean_7"] = df.groupby(["store_id", "product_id"])["units_sold"].transform(
        lambda x: x.shift(1).rolling(7).mean()
    ).values
    df["units_sold_rolling_std_7"] = df.groupby(["store_id", "product_id"])["units_sold"].transform(
        lambda x: x.shift(1).rolling(7).std()
    ).values

    # Price Ratio
    if "competitor_pricing" in df.columns:
        df["price_ratio"] = df["price"] / (df["competitor_pricing"] + 1e-5)
    else:
        df["price_ratio"] = 1.0

    # Date / Calendar features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

    # Categoricals
    cat_cols = ["weather_condition", "seasonality"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    # Drop NaNs created by lag calculations
    df = df.dropna().reset_index(drop=True)
    return df


def main():
    LOG.info("Starting training pipeline")
    client = MongoClient("mongodb://localhost:27017/")
    db_name = "smart_retail_db"

    trans_df = load_collection_to_df(client, db_name, "sales_transactions")
    ext_df = load_collection_to_df(client, db_name, "external_factors")

    if trans_df.empty:
        LOG.error("No transactions found in database.")
        return

    df = prepare_data(trans_df, ext_df)
    LOG.info("Dataset prepared with shape: %s", df.shape)

    feature_cols = [
        "price",
        "discount",
        "units_ordered",
        "units_sold_lag_1",
        "units_sold_lag_7",
        "units_sold_lag_14",
        "units_sold_rolling_mean_7",
        "units_sold_rolling_std_7",
        "price_ratio",
        "day_of_week",
        "month",
        "is_weekend",
        "promotion",
        "epidemic",
        "weather_condition",
        "seasonality",
    ]
    
    # Keep only available feature columns
    feature_cols = [c for c in feature_cols if c in df.columns]
    target_col = "demand"

    X = df[feature_cols]
    y = df[target_col]

    # Chronological Train-Test Split (85% train, 15% test)
    split_idx = int(len(df) * 0.85)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    LOG.info("Training on %d rows, testing on %d rows", len(X_train), len(X_test))

    model = LGBMRegressor(n_estimators=200, learning_rate=0.05, random_state=42, verbose=-1)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    mae = mean_absolute_error(y_test, preds)
    wape = (np.sum(np.abs(y_test - preds)) / np.sum(y_test)) * 100

    print("\n" + "=" * 40)
    print("        MODEL EVALUATION RESULTS        ")
    print("=" * 40)
    print(f" Root Mean Squared Error (RMSE) : {rmse:.2f}")
    print(f" Mean Absolute Error (MAE)      : {mae:.2f}")
    print(f" Weighted Abs % Error (WAPE)    : {wape:.2f}%")
    print("=" * 40 + "\n")

    joblib.dump(model, "model.pkl")
    LOG.info("Model saved successfully as 'model.pkl'")


if __name__ == "__main__":
    main()