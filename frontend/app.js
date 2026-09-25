const API_BASE = "http://127.0.0.1:8000";
const $ = (selector) => document.querySelector(selector);

function showError(message) {
  const alert = $('#error-alert');
  alert.textContent = message;
  alert.hidden = false;
}

function clearError() {
  const alert = $('#error-alert');
  alert.hidden = true;
  alert.textContent = '';
}

function setInventoryStatus(predictedValue) {
  const status = $('#inventory-status');
  if (predictedValue >= 120) {
    status.textContent = 'Elevated';
    status.style.color = '#ff7d7d';
  } else if (predictedValue >= 70) {
    status.textContent = 'Watch';
    status.style.color = '#f6b96b';
  } else {
    status.textContent = 'Stable';
    status.style.color = '#81e7aa';
  }
}

function readPredictionPayload() {
  return {
    store_id: $('#store-id').value.trim(),
    product_id: $('#product-id').value.trim(),
    price: Number.parseFloat($('#price').value),
    discount: Number.parseFloat($('#discount').value),
    units_ordered: Number.parseInt($('#units-ordered').value, 10),
    weather_condition: $('#weather-condition').value.trim(),
    seasonality: $('#seasonality').value.trim()
  };
}

function validatePredictionPayload(payload) {
  if (!payload.store_id || !payload.product_id || !payload.weather_condition || !payload.seasonality) return 'Store ID, Product ID, Weather, and Seasonality are required.';
  if (!Number.isFinite(payload.price) || payload.price <= 0) return 'Price must be greater than 0.';
  if (!Number.isFinite(payload.discount) || payload.discount < 0 || payload.discount > 1) return 'Discount must be between 0 and 1.';
  if (!Number.isInteger(payload.units_ordered) || payload.units_ordered < 0) return 'Units ordered must be a non-negative whole number.';
  return '';
}

async function submitPrediction(event) {
  event.preventDefault();
  clearError();
  const payload = readPredictionPayload();
  const validationError = validatePredictionPayload(payload);
  if (validationError) {
    showError(validationError);
    $('#form-status').textContent = 'Correct the scenario inputs and retry.';
    return;
  }

  const button = $('#predict-button');
  button.disabled = true;
  button.textContent = 'Predicting...';
  $('#form-status').textContent = 'Running XGBoost forecast...';
  try {
    const response = await fetch(`${API_BASE}/predict`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Prediction failed with HTTP ${response.status}`);
    if (typeof result.predicted_demand !== 'number') throw new Error('The API response did not include predicted_demand.');

    const predictedDemand = Number(result.predicted_demand);
    $('#predicted-demand').textContent = predictedDemand.toFixed(1);
    $('#prediction-details').textContent = `${result.store_id} • ${result.product_id} • ${result.status}`;
    $('#form-status').textContent = 'Forecast executed successfully.';
    setInventoryStatus(predictedDemand);
  } catch (error) {
    showError(error.message || 'The prediction request failed.');
    $('#form-status').textContent = 'Prediction request failed.';
    $('#prediction-details').textContent = 'The system could not return a forecast.';
  } finally {
    button.disabled = false;
    button.textContent = 'Predict Demand';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  $('#forecast-form').addEventListener('submit', submitPrediction);
  setInventoryStatus(0);
});
