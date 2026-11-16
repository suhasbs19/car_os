/* charts.js – CAR OS Chart.js helpers */

// ── Global Chart.js defaults ───────────────────────────────────
Chart.defaults.color = '#8ba0b8';
Chart.defaults.borderColor = '#1e2d45';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;

const TEAL    = '#00e5cc';
const CYAN    = '#00cfff';
const HEALTHY = '#10d98a';
const WARN    = '#f59e0b';
const CRIT    = '#ef4444';
const INFO    = '#3b82f6';

const PALETTE = [TEAL, CYAN, '#818cf8', '#f472b6', WARN, '#a78bfa', '#34d399', '#fb923c'];

// ── Health Status Doughnut ────────────────────────────────────
function renderHealthChart(canvasId, healthy, attention, critical) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const total = healthy + attention + critical;
  if (total === 0) {
    ctx.parentElement.innerHTML = '<div class="empty-state" style="padding:40px"><div class="empty-icon">📊</div><p>No vehicle data yet</p></div>';
    return;
  }

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Healthy', 'Attention', 'Critical'],
      datasets: [{
        data: [healthy, attention, critical],
        backgroundColor: [HEALTHY + 'cc', WARN + 'cc', CRIT + 'cc'],
        borderColor:     [HEALTHY, WARN, CRIT],
        borderWidth: 2,
        hoverBorderWidth: 3,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { padding: 16, usePointStyle: true, pointStyleWidth: 10 },
        },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const pct = ((ctx.parsed / total) * 100).toFixed(1);
              return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

// ── Monthly Expense Bar Chart ─────────────────────────────────
function renderExpenseChart(canvasId, monthlyData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (!monthlyData || monthlyData.length === 0) {
    ctx.parentElement.innerHTML = '<div class="empty-state" style="padding:40px"><div class="empty-icon">📊</div><p>No expense data yet</p></div>';
    return;
  }

  const labels  = monthlyData.map(d => d.month);
  const totals  = monthlyData.map(d => d.total);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Expenses (₹)',
        data: totals,
        backgroundColor: TEAL + '55',
        borderColor: TEAL,
        borderWidth: 2,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ' ₹' + ctx.parsed.y.toLocaleString('en-IN'),
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: '#1e2d4588' },
          ticks: { callback: v => '₹' + (v >= 1000 ? (v/1000).toFixed(0)+'K' : v) },
        },
        x: { grid: { display: false } },
      },
    },
  });
}

// ── Maintenance Cost by Category (Pie) ────────────────────────
function renderCategoryChart(canvasId, categoryData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const labels = Object.keys(categoryData);
  const values = Object.values(categoryData);

  if (labels.length === 0) {
    ctx.parentElement.innerHTML = '<div class="empty-state" style="padding:40px"><div class="empty-icon">🔧</div><p>No maintenance data yet</p></div>';
    return;
  }

  new Chart(ctx, {
    type: 'pie',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: PALETTE.map(c => c + 'bb'),
        borderColor: PALETTE,
        borderWidth: 1.5,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { padding: 12, usePointStyle: true, pointStyleWidth: 8, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: ctx => ' ₹' + ctx.parsed.toLocaleString('en-IN'),
          },
        },
      },
    },
  });
}

// ── Fuel Trend Line Chart ─────────────────────────────────────
function renderFuelTrendChart(canvasId, trendData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (!trendData || trendData.length === 0) {
    ctx.parentElement.innerHTML = '<div class="empty-state" style="padding:30px"><div class="empty-icon">⛽</div><p>No fuel data yet</p></div>';
    return;
  }

  const labels = trendData.map(d => d.month);
  const costs  = trendData.map(d => d.cost);
  const dists  = trendData.map(d => d.distance);

  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Cost (₹)',
          data: costs,
          borderColor: TEAL,
          backgroundColor: TEAL + '22',
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: TEAL,
          yAxisID: 'y',
        },
        {
          label: 'Distance (km)',
          data: dists,
          borderColor: CYAN,
          backgroundColor: CYAN + '22',
          fill: false,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: CYAN,
          yAxisID: 'y1',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: {
        y: {
          type: 'linear', position: 'left',
          grid: { color: '#1e2d4566' },
          ticks: { callback: v => '₹' + (v >= 1000 ? (v/1000).toFixed(0)+'K' : v) },
        },
        y1: {
          type: 'linear', position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { callback: v => v + 'km' },
        },
        x: { grid: { display: false } },
      },
    },
  });
}

// ── Valuation comparison bar chart ───────────────────────────
function renderValuationChart(canvasId, vehicles, values) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !vehicles || vehicles.length === 0) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: vehicles,
      datasets: [{
        label: 'Estimated Value (₹)',
        data: values,
        backgroundColor: PALETTE.slice(0, vehicles.length).map(c => c + '88'),
        borderColor: PALETTE.slice(0, vehicles.length),
        borderWidth: 2,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ' ₹' + ctx.parsed.x.toLocaleString('en-IN'),
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: '#1e2d4566' },
          ticks: { callback: v => '₹' + (v >= 1e5 ? (v/1e5).toFixed(1)+'L' : (v/1000).toFixed(0)+'K') },
        },
        y: { grid: { display: false } },
      },
    },
  });
}

// ── Multi-Value (Showroom vs Market vs Resale) Grouped Chart ─
function renderTriValuationChart(canvasId, vehicles, showroomPrices, marketPrices, resaleValues) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !vehicles || vehicles.length === 0) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: vehicles,
      datasets: [
        {
          label: 'Original Showroom (₹)',
          data: showroomPrices,
          backgroundColor: '#3b82f6aa',
          borderColor: '#3b82f6',
          borderWidth: 1.5,
          borderRadius: 4,
        },
        {
          label: 'Current Market Price (₹)',
          data: marketPrices,
          backgroundColor: '#00cfffaa',
          borderColor: '#00cfff',
          borderWidth: 1.5,
          borderRadius: 4,
        },
        {
          label: 'Estimated Resale Value (₹)',
          data: resaleValues,
          backgroundColor: '#00e5ccdd',
          borderColor: '#00e5cc',
          borderWidth: 1.5,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ₹${ctx.parsed.y ? ctx.parsed.y.toLocaleString('en-IN') : 'N/A'}`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: '#1e2d4566' },
          ticks: { callback: v => '₹' + (v >= 1e5 ? (v/1e5).toFixed(1)+'L' : (v/1000).toFixed(0)+'K') },
        },
        x: { grid: { display: false } },
      },
    },
  });
}
