# Smart Retail Demand Forecasting

A full-stack retail demand forecasting system that combines a FastAPI inference service, an XGBoost model, MongoDB prediction logging, Neo4j inventory relationships, and a static Chart.js dashboard.

## Project Overview

The application accepts retail inputs such as store, product, price, discount, order volume, weather, and seasonality. The backend loads the serialized XGBoost model from `model.json`, generates a demand forecast through `POST /predict`, and returns the predicted units to the browser.

Predictions are logged to MongoDB when the database is available. Neo4j stores store-to-product-to-category relationships exposed through `GET /inventory/relationships/{store_id}`. The frontend loads historical sales from `sales_data.csv`, displays the demand outlook with Chart.js, submits forecasts, and renders supply-chain relationships.

## Architecture

```mermaid
flowchart LR
    Browser[Static Chart.js frontend\nlocalhost:3000] -->|POST /predict| API[FastAPI backend\nlocalhost:8000]
    Browser -->|GET /inventory/relationships/{store_id}| API
    Browser -->|Loads historical sales| CSV[sales_data.csv]
    API --> Model[XGBoost inference\nmodel.json]
    API --> Mongo[(MongoDB\npredictions collection)]
    API --> Neo4j[(Neo4j\nStore-Product-Category graph)]
```

### Main components

- **FastAPI backend:** Serves health checks, demand predictions, and inventory graph queries.
- **XGBoost inference:** Loads `model.json` when the API starts and uses it for real-time forecasts.
- **MongoDB:** Stores prediction payloads, forecast values, timestamps, and request status.
- **Neo4j:** Provides store, product, category, and relationship data for supply-chain exploration.
- **Static frontend:** Uses HTML, CSS, JavaScript, and Chart.js. It runs independently from the FastAPI process.
- **Integration suite:** `test_integration.py` verifies MongoDB, the model artifact, the frontend, FastAPI health, CORS, and prediction output.

## System Requirements

### Native execution

- Windows with PowerShell or Command Prompt
- Python 3.10 or newer
- MongoDB running locally on port `27017`
- Neo4j running locally on port `7687`
- A modern web browser
- Optional: Node.js for JavaScript syntax checks

### Containerized execution

- Docker Engine or Docker Desktop
- Docker Compose v2
- A web browser

The supplied Dockerfile uses Python 3.12 for the backend image. Docker Compose starts the backend, frontend, MongoDB, and Neo4j services together.

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

Start Neo4j using the installation method configured on your machine. For a Neo4j Windows service, use:

```powershell
net start Neo4j
```

If Neo4j is managed through Neo4j Desktop, start the configured database from Neo4j Desktop instead. The native backend expects these defaults:

- MongoDB: `mongodb://localhost:27017`
- Neo4j Bolt: `bolt://localhost:7687`
- Neo4j username: `neo4j`
- Neo4j password: `password`

If your local credentials or ports differ, set `MONGODB_URI`, `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` before starting the backend.

### 4. Start the FastAPI backend

Keep the virtual environment activated and run:

```powershell
uvicorn main:app --reload --port 8000
```

The API is available at:

- Health check: `http://localhost:8000/health`
- Interactive API documentation: `http://localhost:8000/docs`
- Prediction endpoint: `http://localhost:8000/predict`
- Inventory graph endpoint: `http://localhost:8000/inventory/relationships/{store_id}`

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
2. Neo4j database
3. FastAPI on port `8000`
4. Static frontend server on port `3000`

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
| Neo4j browser | `http://localhost:7474` | Graph inspection |
| Neo4j Bolt | `localhost:7687` | Backend graph connection |

The Compose configuration injects container-specific connection values into the backend:

- `MONGODB_URI=mongodb://mongodb:27017`
- `MONGODB_DATABASE=smart_retail_db`
- `NEO4J_URI=bolt://neo4j:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=password`
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
