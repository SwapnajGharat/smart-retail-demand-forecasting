const forecastData = {
  milk: { base: 139, elasticity: 0.32 },
  water: { base: 325, elasticity: 0.41 },
  P0001: { base: 115, elasticity: 0.32 },
  P0002: { base: 229, elasticity: 0.32 }
};

let retailRows = [];
let dataSource = 'demo fallback';

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

function number(value) {
  return Number.parseFloat(value) || 0;
}

async function loadRetailData() {
  const sources = ['../sales_data.csv', '/sales_data.csv', 'sales_data.csv'];
  for (const source of sources) {
    try {
      const response = await fetch(source, { cache: 'no-store' });
      if (!response.ok) continue;
      const rows = parseCsv(await response.text());
      if (!rows.length || !rows[0].Date) continue;
      retailRows = rows;
      dataSource = 'sales_data.csv';
      populateFromCsv();
      $('#data-source').textContent = 'sales_data.csv';
      $('#data-source').classList.add('loaded');
      return;
    } catch (error) {
    }
  }
  $('#data-source').textContent = 'Demo preview';
}

function latestByProduct() {
  const latest = new Map();
  retailRows.forEach((row) => {
    const key = row['Product ID'];
    if (!latest.has(key) || row.Date > latest.get(key).Date) latest.set(key, row);
  });
  return [...latest.values()];
}

function populateFromCsv() {
  const latest = latestByProduct();
  const productSelect = $('#product-select');
  productSelect.innerHTML = latest.slice(0, 60).map((row) => `<option value="${row['Product ID']}">${row['Product ID']} · ${row.Category}</option>`).join('');
  const products = Object.fromEntries(latest.map((row) => [row['Product ID'], { base: number(row.Demand), elasticity: 0.32, row }]));
  Object.assign(forecastData, products);
  const tbody = document.querySelector('.inventory-panel tbody');
  tbody.innerHTML = latest.slice(0, 12).map((row) => {
    const inventory = number(row['Inventory Level']);
    const demand = number(row.Demand);
    const cover = demand ? (inventory / demand * 7).toFixed(1) : '0.0';
    const signal = inventory === 0 ? ['critical', 'Stockout risk'] : inventory < demand ? ['risk', 'Restock now'] : ['healthy', 'Healthy'];
    return `<tr data-category="${row.Category}"><td><div class="product-cell"><span class="product-thumb screen">${row['Product ID'].slice(-4)}</span><span><strong>${row['Product ID']}</strong><small>${row.Category}</small></span></div></td><td>${row.Category}</td><td>${inventory} units</td><td>${demand} units</td><td><strong>${cover} days</strong></td><td><span class="table-status ${signal[0]}"><i></i> ${signal[1]}</span></td><td><button class="arrow-button product-action" data-product="${row['Product ID']}" title="Open product"><i data-lucide="arrow-up-right"></i></button></td></tr>`;
  }).join('');
  tbody.querySelectorAll('tr').forEach((row) => row.addEventListener('click', () => toast(`${row.children[0].textContent.trim().split('\n')[0]} details opened`)));
  const categories = [...new Set(retailRows.map((row) => row.Category))];
  document.querySelectorAll('.category-menu button').forEach((button) => button.remove());
  const menu = document.querySelector('.category-menu');
  ['All categories', ...categories].forEach((category) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.textContent = category;
    option.addEventListener('click', () => { document.querySelector('.filter-btn').childNodes[1].textContent = ` ${category} `; filterInventory(category); menu.classList.remove('open'); });
    menu.appendChild(option);
  });
  window.lucide?.createIcons();
  renderScenario();
  updateCsvMetrics();
  updateAttentionSignals(latest);
}

function updateCsvMetrics() {
  const totalDemand = retailRows.reduce((sum, row) => sum + number(row.Demand), 0);
  const totalSold = retailRows.reduce((sum, row) => sum + number(row['Units Sold']), 0);
  const wape = totalDemand ? Math.abs(totalDemand - totalSold) / totalDemand * 100 : 0;
  const cards = document.querySelectorAll('.metric-card');
  if (cards[0]) cards[0].querySelector('strong').innerHTML = `${Math.max(0, 100 - wape).toFixed(1)}<span>%</span>`;
  if (cards[1]) cards[1].querySelector('strong').innerHTML = `${Math.round(totalDemand / Math.max(1, new Set(retailRows.map((row) => row.Date)).size))}<span> units/day</span>`;
}

function updateAttentionSignals(latest) {
  const alertList = $('#alert-list');
  const risks = latest
    .map((row) => ({ row, shortage: number(row.Demand) - number(row['Inventory Level']) }))
    .filter((item) => item.shortage > 0)
    .sort((left, right) => right.shortage - left.shortage)
    .slice(0, 3);
  if (!risks.length) {
    alertList.innerHTML = '<div class="alert-item info"><span class="alert-icon"><i data-lucide="circle-check"></i></span><div><strong>Inventory coverage healthy</strong><p>No immediate stock risks detected</p><small>Based on the latest CSV inventory snapshot</small></div></div>';
  } else {
    alertList.innerHTML = risks.map(({ row }) => {
      const inventory = number(row['Inventory Level']);
      const demand = number(row.Demand);
      const critical = inventory === 0;
      return `<div class="alert-item ${critical ? 'critical' : 'warning'}"><span class="alert-icon"><i data-lucide="${critical ? 'triangle-alert' : 'package-minus'}"></i></span><div><strong>${critical ? 'Stockout risk' : 'Restock recommended'}</strong><p>${row['Product ID']} · ${row.Category} <b>• ${inventory} units</b></p><small>Demand signal: ${demand} units</small></div><button class="arrow-button" title="Open alert"><i data-lucide="arrow-up-right"></i></button></div>`;
    }).join('');
  }
  window.lucide?.createIcons();
}

const $ = (selector) => document.querySelector(selector);
const toast = (message) => {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  window.clearTimeout(window.toastTimer);
  window.toastTimer = window.setTimeout(() => element.classList.remove('show'), 2600);
};

function renderDemandChart(range = 7) {
  const svg = $('#demand-chart');
  let labels = ['Sep 01', 'Sep 02', 'Sep 03', 'Sep 04', 'Sep 05', 'Sep 06', 'Sep 07'];
  let actual = range === 7 ? [121, 138, 130, 160, 147, 174, 166] : [95, 114, 128, 108, 142, 131, 159, 151, 180, 171, 188, 176];
  let forecast = range === 7 ? [126, 134, 139, 151, 154, 162, 169] : [100, 110, 119, 127, 137, 143, 150, 157, 162, 170, 174, 181];
  if (retailRows.length) {
    const byDate = new Map();
    retailRows.forEach((row) => byDate.set(row.Date, (byDate.get(row.Date) || 0) + number(row.Demand)));
    const dates = [...byDate.keys()].sort().slice(-range);
    actual = dates.map((date) => byDate.get(date));
    forecast = actual.map((value, index) => Math.round((actual[Math.max(0, index - 1)] || value) * 1.04));
    labels = dates.map((date) => new Date(`${date}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: '2-digit' }));
  }
  const width = 760, height = 290, left = 42, right = 10, top = 18, bottom = 22;
  const max = Math.max(210, ...actual, ...forecast) * 1.15, x = (index) => left + index * ((width - left - right) / Math.max(1, actual.length - 1));
  const y = (value) => height - bottom - (value / max) * (height - top - bottom);
  const points = (values) => values.map((value, index) => `${x(index)},${y(value)}`).join(' ');
  const bandTop = forecast.map((value, index) => `${x(index)},${y(value + 18)}`).join(' ');
  const bandBottom = forecast.slice().reverse().map((value, index) => `${x(forecast.length - index - 1)},${y(value - 18)}`).join(' ');
  const grid = [50, 100, 150, 200].map((value) => `<line class="chart-grid" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"/><text class="chart-axis" x="0" y="${y(value) + 3}">${value}</text>`).join('');
  const dots = actual.map((value, index) => `<circle class="chart-dot" cx="${x(index)}" cy="${y(value)}" r="3.2"/>`).join('');
  svg.innerHTML = `<defs><linearGradient id="areaFade" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#e9f1eb"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>${grid}<polygon class="chart-band" points="${bandTop} ${bandBottom}"/><polyline class="chart-area" points="${points(actual)} ${width - right},${height - bottom} ${left},${height - bottom}"/><polyline class="actual-line" points="${points(actual)}"/><polyline class="forecast-line" points="${points(forecast)}"/>${dots}`;
  const labelCount = Math.min(7, labels.length);
  const visibleLabels = Array.from({ length: labelCount }, (_, index) => labels[Math.round(index * (labels.length - 1) / Math.max(1, labelCount - 1))]);
  document.querySelector('.chart-labels').innerHTML = visibleLabels.map((label) => `<span>${label}</span>`).join('');
}

function renderScenario() {
  const selected = $('#product-select').value;
  const adjustment = Number($('#price-slider').value);
  const product = forecastData[selected] || { base: 0, elasticity: 0.32 };
  const predicted = Math.round(product.base * (1 - adjustment / 100 * product.elasticity));
  $('#price-value').textContent = `${adjustment > 0 ? '+' : ''}${adjustment}%`;
  $('#baseline-units').textContent = `${product.base} units`;
  $('#predicted-units').textContent = predicted;
  const difference = ((predicted / product.base - 1) * 100).toFixed(1);
  $('#prediction-delta').textContent = `${difference > 0 ? '+' : ''}${difference}% vs baseline`;
  const points = Array.from({ length: 7 }, (_, index) => 52 - Math.sin(index * 1.2 + adjustment / 8) * 13 - index * (adjustment / 80));
  $('#scenario-chart').innerHTML = `<polyline points="${points.map((value, index) => `${index * 34},${value}`).join(' ')}" fill="none" stroke="#4f7c69" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`;
}

function goToView(view) {
  const targets = {
    overview: '#overview',
    forecast: '.forecast-panel',
    performance: '.performance-panel',
    network: '.demand-panel',
    inventory: '.inventory-panel'
  };
  const target = document.querySelector(targets[view] || '#overview');
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  $('#page-title').textContent = view === 'network' ? 'Retail network' : view.charAt(0).toUpperCase() + view.slice(1);
}

function bindAction(button, message) {
  button.addEventListener('click', (event) => {
    event.preventDefault();
    toast(message);
  });
}

function filterInventory(category) {
  document.querySelectorAll('.inventory-panel tbody tr').forEach((row) => {
    const rowCategory = row.children[1]?.textContent.trim();
    row.hidden = category !== 'All categories' && rowCategory !== category;
  });
  toast(`Showing ${category.toLowerCase()}`);
}

function setupCategoryMenu() {
  const button = document.querySelector('.filter-btn');
  if (!button) return;
  const menu = document.createElement('div');
  menu.className = 'category-menu';
  ['All categories', 'Dairy', 'Beverages', 'Electronics'].forEach((category) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.textContent = category;
    option.addEventListener('click', () => {
      button.dataset.category = category;
      button.childNodes[1].textContent = ` ${category} `;
      filterInventory(category);
      menu.classList.remove('open');
    });
    menu.appendChild(option);
  });
  button.parentElement.style.position = 'relative';
  button.parentElement.appendChild(menu);
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    menu.classList.toggle('open');
  });
  document.addEventListener('click', () => menu.classList.remove('open'));
}

async function runPrediction(event) {
  event.preventDefault();
  const button = $('#run-forecast');
  const status = $('#prediction-status');
  button.disabled = true;
  button.innerHTML = '<i data-lucide="loader-circle"></i> Calculating...';
  window.lucide?.createIcons();
  status.textContent = 'Scoring the selected product against the latest store signals...';
  const payload = {
    store_id: $('#store-id').value.trim(),
    product_id: $('#product-select').value,
    price: Number.parseFloat($('#price').value),
    discount: Number.parseFloat($('#discount').value),
    units_ordered: Number.parseInt($('#units-ordered').value, 10),
    weather_condition: $('#weather-condition').value.trim(),
    seasonality: $('#seasonality').value.trim()
  };

  try {
    const response = await fetch('http://localhost:8000/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    if (typeof result.predicted_demand !== 'number') throw new Error('Response did not include predicted_demand');

    $('#predicted-units').textContent = result.predicted_demand.toFixed(1);
    $('#prediction-delta').textContent = 'Backend model prediction';
    status.textContent = `Prediction ready for ${$('#forecast-date').value}.`;
    button.disabled = false;
    button.innerHTML = '<i data-lucide="check"></i> Prediction ready';
    window.lucide?.createIcons();
    window.setTimeout(() => {
      button.innerHTML = '<i data-lucide="play"></i> Run prediction';
      window.lucide?.createIcons();
    }, 1800);
  } catch (error) {
    console.error('Prediction request failed:', error);
    status.textContent = 'Unable to reach the prediction service. Start FastAPI on port 8000 and try again.';
    button.disabled = false;
    button.innerHTML = '<i data-lucide="refresh-cw"></i> Retry prediction';
    window.lucide?.createIcons();
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  window.lucide?.createIcons();
  renderDemandChart();
  renderScenario();
  setupCategoryMenu();
  await loadRetailData();
  renderDemandChart();

  document.querySelectorAll('.segmented button').forEach((button) => button.addEventListener('click', () => {
    document.querySelectorAll('.segmented button').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    renderDemandChart(Number(button.dataset.range));
  }));
  $('#price-slider').addEventListener('input', renderScenario);
  $('#product-select').addEventListener('change', renderScenario);
  $('#forecast-date').addEventListener('change', (event) => {
    renderScenario();
    toast(`Forecast date set to ${event.target.value}`);
  });
  $('#range-date').addEventListener('change', (event) => {
    const date = new Date(`${event.target.value}T00:00:00`);
    $('#range-date-label').textContent = date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
    toast(`Dashboard date changed to ${$('#range-date-label').textContent}`);
  });
  $('#prediction-form').addEventListener('submit', runPrediction);
  $('#export-report').addEventListener('click', () => {
    const accuracy = retailRows.length ? document.querySelector('.metric-card strong').textContent : '93.8%';
    const dailyDemand = retailRows.length ? document.querySelectorAll('.metric-card strong')[1].textContent : '4,286 units';
    const report = `Northstar Retail Intelligence\nMetro Hypermarket - Downtown\nData source: ${dataSource}\n\nForecast accuracy: ${accuracy}\nDemand average: ${dailyDemand}`;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([report], { type: 'text/plain' }));
    link.download = 'northstar-retail-report.txt';
    link.click();
    URL.revokeObjectURL(link.href);
    toast('Report exported successfully');
  });
  document.querySelectorAll('[data-view-link]').forEach((button) => button.addEventListener('click', (event) => {
    event.preventDefault();
    goToView(button.dataset.viewLink);
  }));
  document.querySelectorAll('.nav-item[data-view]').forEach((item) => item.addEventListener('click', (event) => {
    event.preventDefault();
    document.querySelectorAll('.nav-item[data-view]').forEach((nav) => nav.classList.remove('active'));
    item.classList.add('active');
    goToView(item.dataset.view);
  }));
  document.querySelectorAll('.alert-item, .product-action, .inventory-panel tbody tr').forEach((item) => item.addEventListener('click', () => {
    const product = item.dataset.product || item.querySelector('p')?.textContent.split('•')[0].trim() || 'Selected alert';
    toast(`${product} details opened`);
  }));
  document.querySelectorAll('.action-button').forEach((button) => bindAction(button, button.dataset.message));
  document.querySelectorAll('.more-button:not(.action-button)').forEach((button) => bindAction(button, 'More actions opened'));
  document.querySelector('.icon-button[title="Search"]').addEventListener('click', () => toast('Search is ready for products, stores, and forecasts'));
  document.querySelector('.icon-button[title="Notifications"]').addEventListener('click', () => goToView('inventory'));
  document.querySelector('.store-switcher').addEventListener('click', () => toast('Metro Hypermarket · Downtown is the active store'));
  document.querySelector('.date-chip').addEventListener('click', () => toast('Date range selector opened'));
  document.querySelector('.nav-item[href="#settings"]').addEventListener('click', (event) => {
    event.preventDefault();
    toast('Workspace settings opened');
  });
  document.querySelector('.user-row').addEventListener('click', () => toast('Store workspace settings opened'));
});