const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000';
const $ = (selector) => document.querySelector(selector);

let demandChart;
let historicalLabels = [];
let historicalValues = [];
let predictionPoint = null;

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

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines.shift().split(',');
  return lines.map((line) => {
    const values = [];
    let value = '';
    let quoted = false;
    for (const character of line) {
      if (character === '"') quoted = !quoted;
      else if (character === ',' && !quoted) { values.push(value.trim()); value = ''; }
      else value += character;
    }
    values.push(value.trim());
    return Object.fromEntries(headers.map((header, index) => [header, values[index] || '']));
  });
}

async function loadHistoricalSales() {
  try {
    const response = await fetch('sales_data.csv', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Historical sales returned HTTP ${response.status}`);
    const rows = parseCsv(await response.text());
    const totalsByDate = new Map();
    rows.forEach((row) => {
      const units = Number.parseFloat(row['Units Sold']);
      if (row.Date && Number.isFinite(units)) totalsByDate.set(row.Date, (totalsByDate.get(row.Date) || 0) + units);
    });
    const dates = [...totalsByDate.keys()].sort().slice(-14);
    historicalLabels = dates.map(formatDate);
    historicalValues = dates.map((date) => totalsByDate.get(date));
  } catch (error) {
    historicalLabels = [];
    historicalValues = [];
  }
  renderDemandChart();
}

function formatDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
}

function setInventoryBadge(predictedValue) {
  const badge = $('#alert-badge');
  const status = $('#inventory-status');
  if (predictedValue >= 120) {
    badge.textContent = 'Overstock Risk';
    badge.className = 'alert-badge danger';
    status.textContent = 'Elevated';
    status.style.color = '#ff7d7d';
  } else if (predictedValue >= 70) {
    badge.textContent = 'Reorder Required';
    badge.className = 'alert-badge warning';
    status.textContent = 'Watch';
    status.style.color = '#f6b96b';
  } else {
    badge.textContent = 'Optimal';
    badge.className = 'alert-badge neutral';
    status.textContent = 'Stable';
    status.style.color = '#81e7aa';
  }
}

function renderDemandChart() {
  if (!window.Chart) return;
  const threshold = 90;
  const labels = [...historicalLabels, ...(predictionPoint ? [predictionPoint.label] : [])];
  const inventoryThreshold = Array(labels.length).fill(threshold);
  const actual = [...historicalValues, ...(predictionPoint ? [null] : [])];
  const predictions = [
    ...Array(Math.max(0, historicalLabels.length - 1)).fill(null),
    ...(historicalLabels.length ? [historicalValues.at(-1)] : []),
    ...(predictionPoint ? [predictionPoint.value] : [])
  ];

  demandChart?.destroy();
  demandChart = new Chart($('#demand-chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Projected Demand',
          data: predictions,
          borderColor: '#62d0ff',
          backgroundColor: 'rgba(98, 208, 255, 0.12)',
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
          yAxisID: 'y'
        },
        {
          label: 'Inventory Threshold',
          data: inventoryThreshold,
          borderColor: '#f6b96b',
          borderDash: [6, 5],
          pointRadius: 0,
          fill: false,
          tension: 0,
          yAxisID: 'y'
        },
        {
          label: 'Historical Sales',
          data: actual,
          borderColor: '#67e7bf',
          borderDash: [1, 0],
          backgroundColor: 'rgba(103, 231, 191, 0.18)',
          pointRadius: 2,
          fill: false,
          tension: 0.2,
          yAxisID: 'y'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { color: '#dfeaf5', boxWidth: 10, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label(context) {
              const value = Number(context.parsed.y || 0);
              const risk = value > 120 ? 'overstock risk' : value > 70 ? 'reorder pressure' : 'healthy buffer';
              return `${context.dataset.label}: ${value.toFixed(1)} units • ${risk}`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: false,
          grid: { color: 'rgba(148, 179, 197, 0.12)' },
          ticks: { color: '#a8bac6' },
          title: { display: true, text: 'Units', color: '#dfeaf5' }
        },
        x: {
          grid: { display: false },
          ticks: { color: '#a8bac6' }
        }
      }
    }
  });
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
    const response = await fetch(`${API_BASE_URL}/predict`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Prediction failed with HTTP ${response.status}`);
    if (typeof result.predicted_demand !== 'number') throw new Error('The API response did not include predicted_demand.');

    const predictedDemand = Number(result.predicted_demand);
    $('#predicted-demand').textContent = predictedDemand.toFixed(1);
    $('#prediction-details').textContent = `${result.store_id} • ${result.product_id} • ${result.status}`;
    $('#form-status').textContent = 'Forecast executed successfully.';
    setInventoryBadge(predictedDemand);
    predictionPoint = { label: new Date().toLocaleDateString('en-US', { month: 'short', day: '2-digit' }), value: predictedDemand };
    renderDemandChart();
  } catch (error) {
    showError(error.message || 'The prediction request failed.');
    $('#form-status').textContent = 'Prediction request failed.';
    $('#prediction-details').textContent = 'The system could not return a forecast.';
  } finally {
    button.disabled = false;
    button.textContent = 'Predict Demand';
  }
}

function renderGraph(data) {
  const output = $('#graph-output');
  if (!data.nodes?.length) {
    output.innerHTML = '<p class="empty-state">No relationships found for this store.</p>';
    return;
  }
  const nodes = data.nodes.map((node) => {
    const name = node.properties?.product_id || node.properties?.store_id || node.properties?.name || node.id;
    return `<li><span class="node-label">${escapeHtml(node.labels.join(' · '))}</span><strong>${escapeHtml(String(name))}</strong></li>`;
  }).join('');
  const edges = data.edges.map((edge) => `<li><strong>${escapeHtml(edge.type)}</strong><span>${escapeHtml(edge.start_node)} → ${escapeHtml(edge.end_node)}</span></li>`).join('');
  output.innerHTML = `<div><h3>Nodes (${data.nodes.length})</h3><ul>${nodes}</ul></div><div><h3>Edges (${data.edges.length})</h3><ul>${edges || '<li>No edges returned.</li>'}</ul></div>`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

async function fetchGraphRelationships() {
  clearError();
  const storeId = $('#store-id').value.trim();
  if (!storeId) {
    showError('Enter a store ID before querying the graph.');
    return;
  }
  const button = $('#fetch-graph-btn');
  button.disabled = true;
  button.textContent = 'Loading...';
  $('#graph-status').textContent = `Querying ${storeId} inventory graph...`;
  try {
    const response = await fetch(`${API_BASE_URL}/inventory/relationships/${encodeURIComponent(storeId)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Graph query failed with HTTP ${response.status}`);
    renderGraph(result);
    $('#graph-status').textContent = `Loaded ${result.nodes.length} nodes and ${result.edges.length} edges.`;
  } catch (error) {
    showError(error.message || 'The graph request failed.');
    $('#graph-status').textContent = 'Graph query failed.';
  } finally {
    button.disabled = false;
    button.textContent = 'Load Relationships';
  }
}

function bindTabs() {
  document.querySelectorAll('.tab-button').forEach((button) => {
    button.addEventListener('click', () => {
      const selectedTab = button.dataset.tab;
      document.querySelectorAll('.tab-button').forEach((btn) => {
        const active = btn === button;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', String(active));
      });
      document.querySelectorAll('.tab-panel').forEach((panel) => {
        panel.classList.toggle('active', panel.dataset.panel === selectedTab);
      });
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  bindTabs();
  $('#forecast-form').addEventListener('submit', submitPrediction);
  $('#fetch-graph-btn').addEventListener('click', fetchGraphRelationships);
  setInventoryBadge(0);
  renderDemandChart();
  loadHistoricalSales();
});
