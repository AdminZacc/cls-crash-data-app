const DATA_URL = "./output.json";
const severityOrder = ["K", "A", "B", "C", "O", "Unknown"];

const elements = {
  statusText: document.getElementById("statusText"),
  refreshButton: document.getElementById("refreshButton"),
  searchInput: document.getElementById("searchInput"),
  searchStatus: document.getElementById("searchStatus"),
  tableSeverityFilter: document.getElementById("tableSeverityFilter"),
  tableJurisdictionFilter: document.getElementById("tableJurisdictionFilter"),
  tableClearFilters: document.getElementById("tableClearFilters"),
  recordsMetric: document.getElementById("recordsMetric"),
  dateRangeMetric: document.getElementById("dateRangeMetric"),
  injuredMetric: document.getElementById("injuredMetric"),
  killedMetric: document.getElementById("killedMetric"),
  vehiclesMetric: document.getElementById("vehiclesMetric"),
  routeMetric: document.getElementById("routeMetric"),
  severityBars: document.getElementById("severityBars"),
  crashTableBody: document.getElementById("crashTableBody"),
  queryLog: document.getElementById("queryLog"),
  crashMap: document.getElementById("crashMap"),
  mapSeverityFilters: document.getElementById("mapSeverityFilters"),
};

let allRows = [];
let dashboard = null;
let crashMap = null;
let markerLayer = null;
let selectedMapSeverities = new Set(severityOrder);
let selectedMapSeverities = new Set(severityOrder);

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

function formatPopup(row) {
  return `
    <strong>${row.route}</strong><br />
    Severity: ${row.severity}<br />
    Injured: ${row.injured} | Killed: ${row.killed}<br />
    Date: ${row.date}<br />
    Jurisdiction: ${row.jurisdiction}
  `;
}

function toggleSection(button) {
  const targetId = button.getAttribute("data-collapse-target");
  const target = targetId ? document.getElementById(targetId) : null;

  if (!target) return;

  const isHidden = !target.hidden;
  target.hidden = isHidden;
  const expandedLabel =
    button.getAttribute("data-expanded-label") || "Hide section";
  const collapsedLabel =
    button.getAttribute("data-collapsed-label") || "Show section";
  button.textContent = isHidden ? collapsedLabel : expandedLabel;
  button.setAttribute("aria-expanded", String(!isHidden));

  if (!isHidden && target.contains(elements.crashMap) && crashMap) {
    setTimeout(() => crashMap.invalidateSize(), 0);
  }
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
      lat: Number(properties.LAT),
      lon: Number(properties.LON),
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

function getSearchFilteredRows(rows) {
  const query = elements.searchInput.value.trim().toLowerCase();

  if (!query) {
    return rows;
  }

  return rows.filter((row) => {
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
  });
}

function getTableFilteredRows(rows) {
  let filtered = getSearchFilteredRows(rows);

  if (
    elements.tableSeverityFilter &&
    elements.tableSeverityFilter.value !== "All"
  ) {
    filtered = filtered.filter(
      (row) => row.severity === elements.tableSeverityFilter.value,
    );
  }

  if (
    elements.tableJurisdictionFilter &&
    elements.tableJurisdictionFilter.value !== "All"
  ) {
    filtered = filtered.filter(
      (row) =>
        String(row.jurisdiction) === elements.tableJurisdictionFilter.value,
    );
  }

  return filtered;
}

function getMapFilteredRows(rows) {
  return getSearchFilteredRows(rows).filter((row) =>
    selectedMapSeverities.has(row.severity),
  );
}

function initializeMap() {
  if (crashMap || !elements.crashMap || typeof L === "undefined") return;

  crashMap = L.map("crashMap", {
    zoomControl: true,
    scrollWheelZoom: false,
  }).setView([36.7806, -76.1775], 11);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(crashMap);

  markerLayer = L.layerGroup().addTo(crashMap);
}

function syncMapSeverityFilterButtons() {
  if (!elements.mapSeverityFilters) return;

  elements.mapSeverityFilters
    .querySelectorAll("[data-severity]")
    .forEach((button) => {
      const severity = button.dataset.severity;
      const isActive = selectedMapSeverities.has(severity);
      button.classList.toggle("severity-filter-chip--active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
}

function renderMapSeverityFilters(severityCounts) {
  if (!elements.mapSeverityFilters) return;

  elements.mapSeverityFilters.innerHTML = "";

  severityOrder.forEach((severity) => {
    const button = document.createElement("button");
    const count = severityCounts.get(severity) || 0;
    const isActive = selectedMapSeverities.has(severity);

    button.type = "button";
    button.className = `severity-filter-chip ${isActive ? "severity-filter-chip--active" : ""}`;
    button.textContent = `${severity} (${count})`;
    button.setAttribute("aria-pressed", String(isActive));
    button.dataset.severity = severity;

    button.addEventListener("click", () => {
      if (
        selectedMapSeverities.has(severity) &&
        selectedMapSeverities.size === 1
      ) {
        return;
      }

      if (selectedMapSeverities.has(severity)) {
        selectedMapSeverities.delete(severity);
      } else {
        selectedMapSeverities.add(severity);
      }

      syncMapSeverityFilterButtons();
      renderMap(allRows);
    });

    elements.mapSeverityFilters.appendChild(button);
  });
}

function renderMap(rows) {
  initializeMap();

  if (!crashMap || !markerLayer) return;

  markerLayer.clearLayers();

  const bounds = [];
  for (const row of getMapFilteredRows(rows)) {
    if (!Number.isFinite(row.lat) || !Number.isFinite(row.lon)) continue;

    const latLng = [row.lat, row.lon];
    bounds.push(latLng);

    const marker = L.circleMarker(latLng, {
      radius: 6,
      color:
        row.severity === "K"
          ? "#7f1d1d"
          : row.severity === "A"
            ? "#b91c1c"
            : row.severity === "B"
              ? "#d97706"
              : row.severity === "C"
                ? "#0369a1"
                : "#6b7280",
      weight: 2,
      fillColor:
        row.severity === "K"
          ? "#7f1d1d"
          : row.severity === "A"
            ? "#b91c1c"
            : row.severity === "B"
              ? "#d97706"
              : row.severity === "C"
                ? "#0369a1"
                : "#6b7280",
      fillOpacity: 0.82,
    });

    marker.bindPopup(formatPopup(row));
    marker.addTo(markerLayer);
  }

  if (bounds.length > 0) {
    crashMap.fitBounds(bounds, { padding: [20, 20] });
  }
}

function renderTable(rows) {
  const filtered = getTableFilteredRows(rows);
  const query = elements.searchInput.value.trim();

  if (elements.searchStatus) {
    elements.searchStatus.textContent = query
      ? `Showing ${filtered.length} of ${rows.length} records for "${query}"`
      : `Showing all ${rows.length} records`;
  }

  elements.crashTableBody.innerHTML = "";

  if (!filtered.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="7"><div class="empty-state">No records match the current filter.</div></td>`;
    elements.crashTableBody.appendChild(row);
    return filtered;
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

  return filtered;
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
  renderMapSeverityFilters(dashboard.severityCounts);
  if (elements.tableSeverityFilter) {
    elements.tableSeverityFilter.innerHTML =
      '<option value="All">All severities</option>';
    severityOrder.forEach((severity) => {
      const option = document.createElement("option");
      option.value = severity;
      option.textContent = severity;
      elements.tableSeverityFilter.appendChild(option);
    });
  }

  if (elements.tableJurisdictionFilter) {
    const jurisdictions = [
      ...new Set(allRows.map((row) => String(row.jurisdiction))),
    ].sort((a, b) => a.localeCompare(b));
    elements.tableJurisdictionFilter.innerHTML =
      '<option value="All">All jurisdictions</option>';
    jurisdictions.forEach((jurisdiction) => {
      const option = document.createElement("option");
      option.value = jurisdiction;
      option.textContent = jurisdiction;
      elements.tableJurisdictionFilter.appendChild(option);
    });
  }

  syncMapSeverityFilterButtons();
  renderMap(allRows);
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
    renderMap(allRows);
  }
});

if (elements.tableSeverityFilter) {
  elements.tableSeverityFilter.addEventListener("change", () => {
    if (dashboard) {
      renderTable(allRows);
    }
  });
}

if (elements.tableJurisdictionFilter) {
  elements.tableJurisdictionFilter.addEventListener("change", () => {
    if (dashboard) {
      renderTable(allRows);
    }
  });
}

if (elements.tableClearFilters) {
  elements.tableClearFilters.addEventListener("click", () => {
    if (elements.searchInput) elements.searchInput.value = "";
    if (elements.tableSeverityFilter)
      elements.tableSeverityFilter.value = "All";
    if (elements.tableJurisdictionFilter)
      elements.tableJurisdictionFilter.value = "All";
    selectedMapSeverities = new Set(severityOrder);
    syncMapSeverityFilterButtons();
    if (dashboard) {
      renderTable(allRows);
      renderMap(allRows);
    }
  });
}

document.querySelectorAll("[data-collapse-target]").forEach((button) => {
  button.addEventListener("click", () => {
    toggleSection(button);
  });
});

loadData();
