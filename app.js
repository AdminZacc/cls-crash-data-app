const DATA_URL = "./output.json";
const severityOrder = ["K", "A", "B", "C", "O", "Unknown"];

const elements = {
  statusText: document.getElementById("statusText"),
  refreshButton: document.getElementById("refreshButton"),
  searchInput: document.getElementById("searchInput"),
  recordsMetric: document.getElementById("recordsMetric"),
  dateRangeMetric: document.getElementById("dateRangeMetric"),
  injuredMetric: document.getElementById("injuredMetric"),
  killedMetric: document.getElementById("killedMetric"),
  vehiclesMetric: document.getElementById("vehiclesMetric"),
  routeMetric: document.getElementById("routeMetric"),
  severityBars: document.getElementById("severityBars"),
  crashTableBody: document.getElementById("crashTableBody"),
  queryLog: document.getElementById("queryLog"),
};

let allRows = [];
let dashboard = null;

function setStatus(message, isError = false) {
  elements.statusText.textContent = message;
  elements.statusText.style.color = isError
    ? "#ffb4b4"
    : "rgba(255, 255, 255, 0.8)";
}

function safeNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function formatDateTime(value) {
  if (!Number.isFinite(value)) return "Unknown";
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

function severityClass(severity) {
  const normalized = String(severity || "Unknown")
    .trim()
    .toUpperCase();
  return `severity-pill severity-pill--${normalized.toLowerCase() || "unknown"}`;
}

function buildRows(features) {
  const severityCounts = new Map();
  const routeCounts = new Map();
  const rows = [];
  let totalInjured = 0;
  let totalKilled = 0;
  let totalVehicles = 0;
  let earliest = null;
  let latest = null;

  for (const feature of features) {
    const properties = feature?.properties ?? {};
    const crashDt = safeNumber(properties.CRASH_DT);
    const date = crashDt ? new Date(crashDt) : null;

    if (date && !Number.isNaN(date.getTime())) {
      earliest = earliest && earliest < date ? earliest : date;
      latest = latest && latest > date ? latest : date;
    }

    let severity = String(properties.CRASH_SEVERITY || "Unknown")
      .trim()
      .toUpperCase();
    if (!severityOrder.includes(severity)) {
      severity = severity ? severity.slice(0, 1) : "Unknown";
    }
    if (!severityOrder.includes(severity)) {
      severity = "Unknown";
    }

    const route =
      String(properties.ROUTE_OR_STREET_NM || "Unknown").trim() || "Unknown";
    const jurisdiction =
      String(properties.PHYSICAL_JURIS || "Unknown").trim() || "Unknown";
    const injured = safeNumber(properties.PERSONS_INJURED);
    const killed = safeNumber(properties.K_PEOPLE);
    const vehicles = safeNumber(properties.VEH_COUNT);

    totalInjured += injured;
    totalKilled += killed;
    totalVehicles += vehicles;
    severityCounts.set(severity, (severityCounts.get(severity) || 0) + 1);
    routeCounts.set(route, (routeCounts.get(route) || 0) + 1);

    rows.push({
      dateSort: crashDt,
      date: formatDateTime(crashDt),
      severity,
      injured,
      killed,
      vehicles,
      route,
      jurisdiction,
      document: properties.DOCUMENT_NBR ?? "Unknown",
    });
  }

  rows.sort((a, b) => b.dateSort - a.dateSort);
  const topRoute = [...routeCounts.entries()].sort(
    (a, b) => b[1] - a[1],
  )[0] || ["Unknown", 0];

  return {
    records: features.length,
    totalInjured,
    totalKilled,
    averageVehicles: features.length ? totalVehicles / features.length : 0,
    severityCounts,
    topRoute: { name: topRoute[0], count: topRoute[1] },
    dateRange: {
      start: earliest ? earliest.toLocaleString() : "Unknown",
      end: latest ? latest.toLocaleString() : "Unknown",
    },
    rows,
  };
}

function renderSeverityBars(severityCounts, total) {
  elements.severityBars.innerHTML = "";

  severityOrder.forEach((severity, index) => {
    const count = severityCounts.get(severity) || 0;
    const percent = total ? Math.max((count / total) * 100, 3) : 0;
    const row = document.createElement("div");
    row.className = "severity-row";

    const label = document.createElement("div");
    label.className = "severity-row__label";
    label.textContent = severity;

    const track = document.createElement("div");
    track.className = "severity-row__track";

    const bar = document.createElement("div");
    bar.className = `severity-row__bar ${index === 0 ? "severity-row__bar--orange" : ""}`;
    bar.style.width = `${percent}%`;
    track.appendChild(bar);

    const value = document.createElement("div");
    value.className = "severity-row__value";
    value.textContent = count.toString();

    row.append(label, track, value);
    elements.severityBars.appendChild(row);
  });
}

function renderTable(rows) {
  const query = elements.searchInput.value.trim().toLowerCase();
  const filtered = query
    ? rows.filter((row) => {
        const haystack = [
          row.date,
          row.severity,
          row.route,
          row.jurisdiction,
          row.document,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      })
    : rows;

  elements.crashTableBody.innerHTML = "";

  if (!filtered.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="7"><div class="empty-state">No records match the current filter.</div></td>`;
    elements.crashTableBody.appendChild(row);
    return;
  }

  for (const rowData of filtered.slice(0, 50)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rowData.date}</td>
      <td><span class="severity-pill severity-pill--${rowData.severity.toLowerCase()}">${rowData.severity}</span></td>
      <td>${rowData.injured}</td>
      <td>${rowData.killed}</td>
      <td>${rowData.vehicles}</td>
      <td>${rowData.route}</td>
      <td>${rowData.jurisdiction}</td>
    `;
    elements.crashTableBody.appendChild(tr);
  }
}

function renderDashboard(data) {
  dashboard = buildRows(data.features || []);
  allRows = dashboard.rows;

  elements.recordsMetric.textContent = dashboard.records.toString();
  elements.dateRangeMetric.textContent = `${dashboard.dateRange.start} → ${dashboard.dateRange.end}`;
  elements.injuredMetric.textContent = dashboard.totalInjured.toString();
  elements.killedMetric.textContent = dashboard.totalKilled.toString();
  elements.vehiclesMetric.textContent = dashboard.averageVehicles.toFixed(2);
  elements.routeMetric.textContent = `${dashboard.topRoute.name} (${dashboard.topRoute.count})`;

  renderSeverityBars(dashboard.severityCounts, dashboard.records);
  renderTable(allRows);

  elements.queryLog.textContent = JSON.stringify(data, null, 2);
  setStatus(`Loaded ${dashboard.records} crash records from output.json.`);
}

async function loadData() {
  setStatus("Loading output.json...");
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    if (!data || !Array.isArray(data.features)) {
      throw new Error("Invalid GeoJSON structure.");
    }
    renderDashboard(data);
  } catch (error) {
    setStatus(`Failed to load output.json: ${error.message}`, true);
    elements.queryLog.textContent = `Unable to load ${DATA_URL}.\n\n${error.stack || error.message}`;
    elements.crashTableBody.innerHTML =
      '<tr><td colspan="7"><div class="empty-state">No data loaded yet.</div></td></tr>';
  }
}

elements.refreshButton.addEventListener("click", loadData);
elements.searchInput.addEventListener("input", () => {
  if (dashboard) {
    renderTable(allRows);
  }
});

loadData();
