import logging
import time
import joblib

# Set non-interactive Matplotlib backend BEFORE pyplot import to prevent Tkinter crashes
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from lightgbm import LGBMRegressor
from pymongo import MongoClient
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger(__name__)

# --- PyTorch LSTM Architecture ---
class PyTorchLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=1):
        super(PyTorchLSTM, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return out


def train_pytorch_lstm(X_train_seq, y_train_seq, X_test_seq, input_size, epochs=20, batch_size=64):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PyTorchLSTM(input_size=input_size).to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)

    train_dataset = TensorDataset(torch.tensor(X_train_seq, dtype=torch.float32), torch.tensor(y_train_seq, dtype=torch.float32).unsqueeze(1))
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)

    model.train()
    for epoch in range(epochs):
        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        test_tensor = torch.tensor(X_test_seq, dtype=torch.float32).to(device)
        preds = model(test_tensor).cpu().numpy().flatten()

    return preds, model


def load_and_prepare_data():
    LOG.info("Connecting to MongoDB and fetching datasets...")
    client = MongoClient("mongodb://localhost:27017/")
    db = client["smart_retail_db"]

    trans_docs = list(db.sales_transactions.find({}, {"_id": 0}))
    ext_docs = list(db.external_factors.find({}, {"_id": 0}))

    if not trans_docs:
        raise ValueError("sales_transactions collection is empty!")

    trans_df = pd.DataFrame(trans_docs)
    ext_df = pd.DataFrame(ext_docs)

    if not ext_df.empty and "store_id" in ext_df.columns and "date" in ext_df.columns:
        df = pd.merge(trans_df, ext_df, on=["store_id", "date"], how="left")
    else:
        df = trans_df.copy()

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["store_id", "product_id", "date"]).reset_index(drop=True)

    # Feature Engineering
    df["units_sold_lag_1"] = df.groupby(["store_id", "product_id"])["units_sold"].shift(1)
    df["units_sold_lag_7"] = df.groupby(["store_id", "product_id"])["units_sold"].shift(7)
    df["units_sold_lag_14"] = df.groupby(["store_id", "product_id"])["units_sold"].shift(14)

    df["units_sold_rolling_mean_7"] = (
        df.groupby(["store_id", "product_id"])["units_sold"]
        .transform(lambda x: x.shift(1).rolling(7).mean())
        .values
    )
    df["units_sold_rolling_std_7"] = (
        df.groupby(["store_id", "product_id"])["units_sold"]
        .transform(lambda x: x.shift(1).rolling(7).std())
        .values
    )

    if "competitor_pricing" in df.columns:
        df["price_ratio"] = df["price"] / (df["competitor_pricing"] + 1e-5)
    else:
        df["price_ratio"] = 1.0

    df["day_of_week"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

    df = df.dropna().reset_index(drop=True)
    return df


def create_lstm_sequences(X_data, y_data, seq_length=7):
    X_seq, y_seq = [], []
    for i in range(len(X_data) - seq_length):
        X_seq.append(X_data[i : i + seq_length])
        y_seq.append(y_data[i + seq_length])
    return np.array(X_seq), np.array(y_seq)


def benchmark_models():
    df = load_and_prepare_data()

    num_cols = [
        "price", "discount", "units_ordered", "units_sold_lag_1",
        "units_sold_lag_7", "units_sold_lag_14", "units_sold_rolling_mean_7",
        "units_sold_rolling_std_7", "price_ratio", "day_of_week", "month",
        "is_weekend", "promotion", "epidemic",
    ]
    cat_cols = ["weather_condition", "seasonality"]

    feature_cols = [c for c in num_cols + cat_cols if c in df.columns]
    target_col = "demand"

    X = df[feature_cols]
    y = df[target_col]

    split_idx = int(len(df) * 0.85)
    X_train, X_test = X.iloc[:split_idx].copy(), X.iloc[split_idx:].copy()
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    LOG.info(f"Training rows: {len(X_train)} | Testing rows: {len(X_test)}")

    # Preprocessing
    X_train_lgb = X_train.copy()
    X_test_lgb = X_test.copy()
    for c in cat_cols:
        if c in X_train_lgb.columns:
            X_train_lgb[c] = X_train_lgb[c].astype("category")
            X_test_lgb[c] = X_test_lgb[c].astype("category")

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), [c for c in num_cols if c in X_train.columns]),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), [c for c in cat_cols if c in X_train.columns]),
        ]
    )

    X_train_encoded = preprocessor.fit_transform(X_train)
    X_test_encoded = preprocessor.transform(X_test)

    # Models list
    models = {
        "LightGBM Regressor": (LGBMRegressor(n_estimators=200, learning_rate=0.05, random_state=42, verbose=-1), X_train_lgb, X_test_lgb),
        "XGBoost Regressor": (XGBRegressor(n_estimators=200, learning_rate=0.05, random_state=42), X_train_encoded, X_test_encoded),
        "Random Forest": (RandomForestRegressor(n_estimators=100, max_depth=15, random_state=42, n_jobs=-1), X_train_encoded, X_test_encoded),
        "Baseline (Mean)": (DummyRegressor(strategy="mean"), X_train_encoded, X_test_encoded),
    }

    results = []
    best_model_obj = None
    best_wape = float("inf")

    # Train standard ML models
    for name, (model, train_data, test_data) in models.items():
        start_time = time.time()
        model.fit(train_data, y_train)
        train_time = time.time() - start_time

        preds = model.predict(test_data)

        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        wape = (np.sum(np.abs(y_test - preds)) / np.sum(y_test)) * 100
        accuracy = max(0.0, 100.0 - wape)

        results.append({
            "Model": name,
            "Accuracy (%)": round(accuracy, 2),
            "WAPE (%)": round(wape, 2),
            "MAE": round(mae, 2),
            "RMSE": round(rmse, 2),
            "Train Time (s)": round(train_time, 2),
        })

        if wape < best_wape:
            best_wape = wape
            best_model_obj = model

    # Train LSTM Neural Network
    LOG.info("Training LSTM Neural Network...")
    seq_length = 7
    X_train_seq, y_train_seq = create_lstm_sequences(X_train_encoded, y_train.values, seq_length)
    X_test_seq, y_test_seq = create_lstm_sequences(X_test_encoded, y_test.values, seq_length)

    start_time = time.time()
    lstm_preds, _ = train_pytorch_lstm(X_train_seq, y_train_seq, X_test_seq, input_size=X_train_encoded.shape[1])
    lstm_time = time.time() - start_time

    mae_lstm = mean_absolute_error(y_test_seq, lstm_preds)
    rmse_lstm = np.sqrt(mean_squared_error(y_test_seq, lstm_preds))
    wape_lstm = (np.sum(np.abs(y_test_seq - lstm_preds)) / np.sum(y_test_seq)) * 100
    accuracy_lstm = max(0.0, 100.0 - wape_lstm)

    results.append({
        "Model": "LSTM Neural Network",
        "Accuracy (%)": round(accuracy_lstm, 2),
        "WAPE (%)": round(wape_lstm, 2),
        "MAE": round(mae_lstm, 2),
        "RMSE": round(rmse_lstm, 2),
        "Train Time (s)": round(lstm_time, 2),
    })

    results_df = pd.DataFrame(results).sort_values("Accuracy (%)", ascending=False).reset_index(drop=True)

    # Print Table
    print("\n" + "=" * 80)
    print("                     MODEL ACCURACY COMPARISON TABLE                       ")
    print("=" * 80)
    print(results_df.to_string(index=False))
    print("=" * 80 + "\n")

    # Save best tree model as pkl artifact
    joblib.dump(best_model_obj, "model.pkl")
    LOG.info("Best tree model saved as 'model.pkl'")

    plot_comparison_charts(results_df)


def plot_comparison_charts(df):
    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Model Evaluation & Comparison Dashboard (Tree vs Neural Net)", fontsize=16, fontweight="bold")

    # 1. Accuracy (%) Chart
    sns.barplot(x="Accuracy (%)", y="Model", data=df, ax=axes[0, 0], palette="crest")
    axes[0, 0].set_title("Overall Accuracy (%) - Higher is Better", fontweight="bold")
    axes[0, 0].set_xlim(0, 100)
    for p in axes[0, 0].patches:
        axes[0, 0].annotate(f"{p.get_width():.2f}%", (p.get_width() - 12, p.get_y() + p.get_height() / 2),
                            ha="center", va="center", color="white", fontweight="bold")

    # 2. WAPE (%) Chart
    sns.barplot(x="WAPE (%)", y="Model", data=df, ax=axes[0, 1], palette="flare")
    axes[0, 1].set_title("Weighted Abs % Error (WAPE) - Lower is Better", fontweight="bold")
    for p in axes[0, 1].patches:
        axes[0, 1].annotate(f"{p.get_width():.2f}%", (p.get_width() / 2, p.get_y() + p.get_height() / 2),
                            ha="center", va="center", color="white", fontweight="bold")

    # 3. MAE & RMSE Errors
    error_df = df.melt(id_vars=["Model"], value_vars=["MAE", "RMSE"], var_name="Metric", value_name="Units")
    sns.barplot(x="Units", y="Model", hue="Metric", data=error_df, ax=axes[1, 0], palette="Set2")
    axes[1, 0].set_title("Absolute Errors (MAE vs RMSE)", fontweight="bold")

    # 4. Training Execution Time
    sns.barplot(x="Train Time (s)", y="Model", data=df, ax=axes[1, 1], palette="Spectral")
    axes[1, 1].set_title("Training Execution Time (Seconds)", fontweight="bold")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig("model_comparison_chart.png", dpi=300)
    LOG.info("Comparison chart saved as 'model_comparison_chart.png'")


if __name__ == "__main__":
    benchmark_models()