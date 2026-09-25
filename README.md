# Smart Retail Demand Forecasting

A full-stack retail demand forecasting system that combines a FastAPI inference service, an XGBoost model, MongoDB prediction logging, and a static Chart.js dashboard.

## Project Overview

The application accepts retail inputs such as store, product, price, discount, order volume, weather, and seasonality. The backend loads the serialized XGBoost model from `model.json`, generates a demand forecast through `POST /predict`, and returns the predicted units to the browser.

Predictions are logged to MongoDB when the database is available. The frontend loads historical sales from `sales_data.csv`, displays the demand outlook with Chart.js, and submits forecasts.

## Architecture

```mermaid
flowchart LR
    Browser[Static Chart.js frontend\nlocalhost:3000] -->|POST /predict| API[FastAPI backend\nlocalhost:8000]
    Browser -->|Loads historical sales| CSV[sales_data.csv]
    API --> Model[XGBoost inference\nmodel.json]
    API --> Mongo[(MongoDB\npredictions collection)]
```

### Main components

- **FastAPI backend:** Serves health checks and demand predictions.
- **XGBoost inference:** Loads `model.json` when the API starts and uses it for real-time forecasts.
- **MongoDB:** Stores prediction payloads, forecast values, timestamps, and request status.
- **Static frontend:** Uses HTML, CSS, JavaScript, and Chart.js. It runs independently from the FastAPI process.
- **Integration suite:** `test_integration.py` verifies MongoDB, the model artifact, the frontend, FastAPI health, CORS, and prediction output.

## System Requirements

### Native execution

- Windows with PowerShell or Command Prompt
- Python 3.10 or newer
- MongoDB running locally on port `27017`
- A modern web browser
- Optional: Node.js for JavaScript syntax checks

### Containerized execution

- Docker Engine or Docker Desktop
- Docker Compose v2
- A web browser

The supplied Dockerfile uses Python 3.12 for the backend image. Docker Compose starts the backend, frontend, and MongoDB services together.

## Native Local Execution

### 1. Open the project directory

```powershell
cd "D:\ADBMS PROJECT"
```

### 2. Create and activate the virtual environment

Create the environment once if `.venv` does not exist:

```powershell
py -3.10 -m venv .venv
```

Activate it in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

For Command Prompt, use:

```bat
.venv\Scripts\activate.bat
```

Install the Python dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Start the local database services

Start MongoDB as a Windows service:

```powershell
net start MongoDB
```

The native backend expects this default:

- MongoDB: `mongodb://localhost:27017`

If your MongoDB credentials or port differ, set the corresponding MongoDB environment variables before starting the backend.

### 4. Start the FastAPI backend

Keep the virtual environment activated and run:

```powershell
uvicorn main:app --reload --port 8000
```

The API is available at:

- Health check: `http://localhost:8000/health`
- Interactive API documentation: `http://localhost:8000/docs`
- Prediction endpoint: `http://localhost:8000/predict`

### 5. Start the static frontend

Open a second terminal in the project root and run:

```powershell
python -m http.server 3000 --directory frontend
```

Open the dashboard at:

```text
http://localhost:3000
```

The frontend expects the FastAPI backend at `http://localhost:8000`.

### Native process summary

Run these processes during local development:

1. MongoDB service
2. FastAPI on port `8000`
3. Static frontend server on port `3000`

## Containerized Execution

Docker Compose runs the complete application stack, including the databases:

```powershell
docker-compose up --build
```

After the health checks pass, open:

```text
http://localhost:3000
```

Compose publishes these services:

| Service | Host address | Purpose |
| --- | --- | --- |
| Frontend | `http://localhost:3000` | Static Chart.js dashboard |
| Backend | `http://localhost:8000` | FastAPI inference API |
| FastAPI docs | `http://localhost:8000/docs` | Interactive API documentation |
| MongoDB | `localhost:27017` | Prediction persistence |

The Compose configuration injects container-specific connection values into the backend:

- `MONGODB_URI=mongodb://mongodb:27017`
- `MONGODB_DATABASE=smart_retail_db`
- `MODEL_PATH=/app/model.json`

To stop the stack, press `Ctrl+C` in the Compose terminal. To stop and remove the containers while preserving named volumes:

```powershell
docker-compose down
```

To remove the containers and persisted database volumes as well:

```powershell
docker-compose down -v
```

## Automated Verification

The integration suite requires the following to be running:

- MongoDB on `localhost:27017`
- FastAPI on `localhost:8000`
- Static frontend on `localhost:3000`
- `model.json` present in the project root

With the virtual environment activated, execute:

```powershell
python test_integration.py
```

The suite checks:

- MongoDB connectivity and access to `smart_retail_db`
- XGBoost loading of `model.json`
- Frontend availability and HTML response
- FastAPI `/health` response
- CORS access for `http://localhost:3000`
- Successful `/predict` response with a positive numeric `predicted_demand`

A successful run ends with:

```text
[PASS] Complete connection pipeline validated.
```

## API Request Example

```json
{
  "store_id": "STORE_01",
  "product_id": "PROD_01",
  "price": 49.99,
  "discount": 0.1,
  "units_ordered": 50,
  "weather_condition": "Clear",
  "seasonality": "None"
}
```

Send it to the backend with:

```powershell
curl.exe -X POST http://localhost:8000/predict `
  -H "Content-Type: application/json" `
  -d "{\"store_id\":\"STORE_01\",\"product_id\":\"PROD_01\",\"price\":49.99,\"discount\":0.1,\"units_ordered\":50,\"weather_condition\":\"Clear\",\"seasonality\":\"None\"}"
```

## Repository Layout

```text
.
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── compare_models.py
├── docker-compose.yml
├── Dockerfile
├── ingest.py
├── main.py
├── model.json
├── requirements.txt
├── sales_data.csv
├── smart_retail_schema.json
├── test_integration.py
└── train.py
```
