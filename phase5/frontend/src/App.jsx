import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

let geoJsonPromise = null;

const loadGeoJsonOnce = () => {
  if (!geoJsonPromise) {
    geoJsonPromise = fetch("/reference/milano-grid.geojson")
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `GeoJSON request failed (${response.status})`
          );
        }

        return response.json();
      });
  }

  return geoJsonPromise;
};

const pages = [
  { id: "overview", label: "Overview", icon: "◈" },
  { id: "grid", label: "Grid Activity", icon: "▦" },
  { id: "hotspots", label: "Hotspots", icon: "△" },
  { id: "risk", label: "Risk Analysis", icon: "◎" },
  { id: "operations", label: "Operations", icon: "⌁" },
];

function App() {
  const [activePage, setActivePage] = useState("overview");
  const [selectedGridId, setSelectedGridId] = useState(""); 
  const [geoJson, setGeoJson] = useState(null);
  const [sidebarWidth, setSidebarWidth] = useState(255);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(`${API_BASE_URL}/network/summary`);

        if (!response.ok) {
          throw new Error(`API request failed (${response.status})`);
        }

        const data = await response.json();
        setSummary(data);
      } catch (err) {
        setError(
          err.message ||
            "Unable to connect to Network Intelligence API."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
  }, []);

//   useEffect(() => {
//   const fetchGeoJson = async () => {
//     try {
//       const response = await fetch(
//         "/reference/milano-grid.geojson"
//       );

//       if (!response.ok) {
//         throw new Error(
//           `GeoJSON request failed (${response.status})`
//         );
//       }

//       const data = await response.json();
//       setGeoJson(data);
//     } catch (err) {
//       console.error("Unable to load Milan grid GeoJSON:", err);
//     }
//   };

//   fetchGeoJson();
// }, []);
useEffect(() => {
  loadGeoJsonOnce()
    .then((data) => {
      setGeoJson(data);
    })
    .catch((err) => {
      console.error(
        "Unable to load Milan grid GeoJSON:",
        err
      );
    });
}, []);

const openGridExplorer = (gridId) => {
  setSelectedGridId(String(gridId));
  setActivePage("grid");
};

  return (
    <div className="app">
      <aside
        className="sidebar"
        style={{ width: `${sidebarWidth}px` }}
      >
       <div className="brand">
        <div className="brand-mark">N</div>
          <div>
            <h1>NETWORK INTELLIGENCE</h1>
            <span>MILESTONE 1</span>
          </div>
        </div>

        <nav>
          {pages.map((page) => (
            <button
              key={page.id}
              className={`nav-item ${
                activePage === page.id ? "active" : ""
              }`}
              onClick={() => setActivePage(page.id)}
            >
              <span>{page.icon}</span>
              {page.label}
            </button>
          ))}
        </nav>

        <div className="system-status">
          <div className="status-dot" />

          <div>
            <strong>SYSTEM ONLINE</strong>
            <small>API CONNECTION ACTIVE</small>
          </div>
        </div>
      </aside>

          <div
  className="sidebar-resizer"
  onMouseDown={(event) => {
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = sidebarWidth;

    const handleMouseMove = (moveEvent) => {
      const newWidth = Math.min(
        400,
        Math.max(200, startWidth + moveEvent.clientX - startX)
      );

      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }}
/>
      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">NETWORK OPERATIONS CENTER</p>

            <h2>
              {pages.find((page) => page.id === activePage)?.label}
            </h2>
          </div>

          <div className="live-badge">
            <span /> LIVE DATA
          </div>
        </header>

        <section className="content">
          {activePage === "overview" && (
            <Overview
              summary={summary}
              loading={loading}
              error={error}
            />
          )}

          {/* {activePage === "grid" &&  (
            <PlaceholderPage
              title="Grid Activity"
              description="Grid-level network activity analysis will be connected to API 2."
              endpoint="/network/grid/{grid_id}"
            />
          )} */}
          {activePage === "grid" && (
          <GridExplorer initialGridId={selectedGridId} />)}

          {/* {activePage === "hotspots" && (
            <PlaceholderPage
              title="Hotspots"
              description="Network hotspots and alerts will be connected to API 3."
              endpoint="/network/hotspots"
            />
          )} */}
          {activePage === "hotspots" && (
            <HotspotsPage
            geoJson={geoJson}
            onOpenGrid={openGridExplorer}/>)}
          
          {activePage === "risk" && <RiskPage />}

          {/* {activePage === "risk" && (
            <PlaceholderPage
              title="Risk Analysis"
              description="ML features and network risk prediction will be connected to APIs 4 and 5."
              endpoint="/network/grid/{grid_id}/features"
            />
          )} */}

          {activePage === "operations" && (
            <PlaceholderPage
              title="Operations"
              description="Pipeline health and grid location will be connected to API 6."
              endpoint="/pipeline/status"
            />
          )}
        </section>
      </main>
    </div>
  );
}

function Overview({ summary, loading, error }) {
  if (loading) {
    return (
      <div className="state-card">
        <div className="spinner" />

        <h3>Loading network intelligence</h3>

        <p>
          Connecting to the FastAPI analytics service...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="state-card error-card">
        <div className="error-icon">!</div>

        <h3>Network API unavailable</h3>

        <p>{error}</p>

        <small>
          Verify that the FastAPI service is running on port 8000.
        </small>
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  return (
    <>
      <div className="hero-card">
        <div>
          <p className="eyebrow">
            CURRENT NETWORK SNAPSHOT
          </p>

          <h3>
            Network intelligence is operational
          </h3>

          <p className="muted">
            Live analytical data received successfully from
            the Phase 4 FastAPI service.
          </p>
        </div>

        <div className="connection">
          <span />
          API CONNECTED
        </div>
      </div>

      <div className="metrics">
        <Metric
          label="Total Activity"
          value={summary.total_activity}
          accent="primary"
        />

        <Metric
          label="Active Grids"
          value={summary.active_grids.toLocaleString()}
          accent="blue"
        />

        <Metric
          label="Top Grid"
          value={summary.top_grid}
          accent="purple"
        />

        <Metric
          label="Peak Hour"
          value={summary.peak_hour}
          accent="orange"
        />
      </div>

      <div className="details-card">
        <div>
          <p className="eyebrow">
            REPORTING TIMESTAMP
          </p>

          <strong>{summary.as_of}</strong>
        </div>

        <div className="api-source">
          SOURCE
          <strong>/network/summary</strong>
        </div>
      </div>
    </>
  );
}

function GridExplorer({ initialGridId = "" }) {
  const [gridId, setGridId] =  useState(
  String(initialGridId || "")
);
  const [activity, setActivity] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchGridActivity = async (grid) => {
  const trimmedGridId = String(grid).trim();

  if (!trimmedGridId) {
    setError("Enter a grid ID to continue.");
    setActivity(null);
    return;
  }

  setLoading(true);
  setError("");
  setActivity(null);

  try {
    const response = await fetch(
      `${API_BASE_URL}/network/grid/${encodeURIComponent(
        trimmedGridId
      )}`
    );

    if (response.status === 404) {
      throw new Error(`Grid ${trimmedGridId} not found.`);
    }

    if (!response.ok) {
      throw new Error(
        `API request failed (${response.status})`
      );
    }

    const data = await response.json();
    setActivity(data);
  } catch (err) {
    setError(
      err.message || "Unable to load grid activity."
    );
  } finally {
    setLoading(false);
  }
};

const searchGrid = async (event) => {
  event.preventDefault();
  await fetchGridActivity(gridId);
};

useEffect(() => {
  if (initialGridId) {
    setGridId(String(initialGridId));
    fetchGridActivity(initialGridId);
  }
}, [initialGridId]);

  return (
    <div className="grid-explorer">
      <div className="explorer-header">
        <div>
          <p className="eyebrow">GRID-LEVEL ANALYSIS</p>
          <h3>Explore network activity</h3>
          <p className="muted">
            Search a grid to view its most recent 24-hour activity profile.
          </p>
        </div>

        <div className="explorer-endpoint">
          <span>API ENDPOINT</span>
          <strong>/network/grid/{"{grid_id}"}</strong>
        </div>
      </div>

      <form className="grid-search" onSubmit={searchGrid}>
        <div className="search-field">
          <label htmlFor="grid-id">Grid ID</label>
          <input
            id="grid-id"
            type="number"
            // min="1"
            // max="10000"
            placeholder="e.g. 4821"
            value={gridId}
            onChange={(event) => setGridId(event.target.value)}
          />
        </div>

        <button type="submit" disabled={loading}>
          {loading ? "Loading..." : "Search Grid"}
        </button>
      </form>

      {loading && (
        <div className="grid-state">
          <div className="spinner" />
          <h4>Loading grid activity</h4>
          <p>Retrieving the latest 24-hour network profile...</p>
        </div>
      )}

      {!loading && error && (
        <div className="grid-state grid-error">
          <div className="error-icon">!</div>
          <h4>Grid not found</h4>
          <p>{error}</p>
          <small>
            Check the grid ID and try again.
          </small>
        </div>
      )}

      {!loading && !error && activity && (
        <div className="activity-section">
          <div className="activity-summary">
            <div>
              <span>GRID</span>
              <strong>{activity.grid_id}</strong>
            </div>

            <div>
              <span>REPORTING TIMESTAMP</span>
              <strong>{activity.as_of}</strong>
            </div>

            <div>
              <span>DATA POINTS</span>
              <strong>{activity.points.length}</strong>
            </div>
          </div>

          <div className="series-legend">
            <span className="legend-sms">SMS Activity</span>
            <span className="legend-call">Call Activity</span>
            <span className="legend-internet">Internet Activity</span>
            <span className="legend-total">Total Activity</span>
          </div>

          <div className="activity-table-wrapper">
            <table className="activity-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>SMS Activity</th>
                  <th>Call Activity</th>
                  <th>Internet Activity</th>
                  <th>Total Activity</th>
                </tr>
              </thead>

              <tbody>
                {activity.points.map((point) => (
                  <tr key={point.timestamp}>
                    <td>{point.timestamp}</td>
                    <td>{point.sms_activity}</td>
                    <td>{point.call_activity}</td>
                    <td>{point.internet_activity}</td>
                    <td>{point.total_activity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, accent }) {
  return (
    <div className={`metric-card ${accent}`}>
      <div className="metric-label">
        {label}
      </div>

      <div className="metric-value">
        {value}
      </div>

      <div className="metric-line" />
    </div>
  );
}

function formatActivity(value) {
  return Number(value).toFixed(4);
}

function HotspotsPage({ geoJson, onOpenGrid }) {
  const [hotspots, setHotspots] = useState([]);
  const [alerts, setAlerts] = useState([]);

  const [limit, setLimit] = useState(10);
  const [severity, setSeverity] = useState("ALL");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchOperationalData = async () => {
      try {
        setLoading(true);
        setError("");

        const [hotspotResponse, alertResponse] =
          await Promise.all([
            fetch(
              `${API_BASE_URL}/network/hotspots?limit=10000`
            ),
            fetch(
              `${API_BASE_URL}/network/alerts?limit=1000`
            ),
          ]);

        if (!hotspotResponse.ok) {
          throw new Error(
            `Hotspots API request failed (${hotspotResponse.status})`
          );
        }

        if (!alertResponse.ok) {
          throw new Error(
            `Alerts API request failed (${alertResponse.status})`
          );
        }

        const hotspotData = await hotspotResponse.json();
        const alertData = await alertResponse.json();

        setHotspots(hotspotData.results || []);
        setAlerts(alertData.results || []);
      } catch (err) {
        setError(
          err.message ||
            "Unable to load hotspot and alert data."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchOperationalData();
  }, []);

  const alertByGrid = new Map();

alerts.forEach((alert) => {
  const gridId = String(alert.grid_id);
  const current = alertByGrid.get(gridId);

  if (
    !current ||
    new Date(alert.timestamp) >
      new Date(current.timestamp)
  ) {
    alertByGrid.set(gridId, alert);
  }
});

  const getOperationalStatus = (gridId) => {
  const alert = alertByGrid.get(String(gridId));

  if (!alert) {
    return "NORMAL";
  }

  if (alert.severity === "HIGH") {
    return "HIGH";
  }

  if (alert.severity === "MEDIUM") {
    return "ATTENTION";
  }

  return "NORMAL";
};

const hotspotRows = hotspots.map((hotspot) => ({
  ...hotspot,
  operationalStatus: getOperationalStatus(hotspot.grid_id),
  alert:
    alertByGrid.get(String(hotspot.grid_id)) || null,
}));

const filteredHotspots = hotspotRows
  .filter((item) => {
    if (severity === "ALL") {
      return true;
    }

    return item.operationalStatus === severity;
  })
  .sort((a, b) => {
    return (
      Number(b.total_activity) -
      Number(a.total_activity)
    );
  })
  .slice(0, Number(limit));

  const filteredAlerts = alerts.filter((alert) => {
    if (severity === "ALL") {
      return true;
    }

    if (severity === "HIGH") {
      return alert.severity === "HIGH";
    }

    if (severity === "ATTENTION") {
      return alert.severity === "MEDIUM";
    }

    if (severity === "NORMAL") {
      return alert.severity === "LOW";
    }

    return true;
  });

  const topHotspot = hotspots[0];

  return (
    <div className="hotspots-page">
      <div className="explorer-header">
        <div>
          <p className="eyebrow">OPERATIONAL INTELLIGENCE</p>
          <h3>Hotspots & Milan Map</h3>
          <p>
            Prioritized network activity and alert areas
            across the Milan grid.
          </p>
        </div>

        <div className="explorer-endpoint">
          <span>DATA SOURCES</span>
          <code>/network/hotspots</code>
          <code>/network/alerts</code>
        </div>
      </div>

      <div className="hotspot-controls">
        <div className="control-field">
          <label htmlFor="hotspot-limit">
            Display Limit
          </label>

          <select
            id="hotspot-limit"
            value={limit}
            onChange={(event) =>
              setLimit(Number(event.target.value))
            }
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </div>

        <div className="control-field">
          <label htmlFor="hotspot-severity">
            Severity
          </label>

          <select
            id="hotspot-severity"
            value={severity}
            onChange={(event) =>
              setSeverity(event.target.value)
            }
          >
            <option value="ALL">All Statuses</option>
            <option value="HIGH">High</option>
            <option value="ATTENTION">Attention</option>
            <option value="NORMAL">Normal</option>
          </select>
        </div>

        <div className="status-legend">
          <StatusBadge status="HIGH" />
          <StatusBadge status="ATTENTION" />
          <StatusBadge status="NORMAL" />
        </div>
      </div>

      {error && (
        <div className="grid-state error-state">
          <strong>Unable to load operational data</strong>
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="grid-state">
          <strong>Loading hotspots and alerts...</strong>
          <span>Connecting to Network Intelligence APIs.</span>
        </div>
      )}

      {!loading && !error && (
        <>
          <section className="hotspot-layout">
            <div className="hotspot-table-panel">
              <div className="panel-heading">
                <div>
                  <span className="panel-kicker">
                    RANKED ACTIVITY
                  </span>
                  <h4>Top Network Hotspots</h4>
                </div>

                {topHotspot && (
                  <span className="top-hotspot-label">
                    TOP GRID {topHotspot.grid_id}
                  </span>
                )}
              </div>

              <div className="activity-table-wrapper">
                <table className="activity-table hotspot-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Grid</th>
                      <th>Total Activity</th>
                      <th>Status</th>
                      <th>Timestamp</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredHotspots.map((item, index) => (
                      <tr
                        key={`${item.grid_id}-${item.timestamp}`}
                        onClick={() =>
                          onOpenGrid(item.grid_id)
                        }
                        className={
                          String(item.grid_id) ===
                          String(topHotspot?.grid_id)
                            ? "top-hotspot-row"
                            : ""
                        }
                      >
                        <td>{index + 1}</td>

                        <td>
                          <strong>{item.grid_id}</strong>
                        </td>

                       <td>
                        {formatActivity(item.total_activity)}
                      </td>

                        <td>
                          <StatusBadge
                            status={item.operationalStatus}
                          />
                        </td>

                        <td>{item.timestamp}</td>
                      </tr>
                    ))}

                    {filteredHotspots.length === 0 && (
                      <tr>
                        <td
                          colSpan="5"
                          className="empty-table"
                        >
                          No network grids match the selected
                          severity.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="map-panel">
              <div className="panel-heading">
                <div>
                  <span className="panel-kicker">
                    GEOSPATIAL VIEW
                  </span>
                  <h4>Milan Network Grid</h4>
                </div>
              </div>

              <div className="map-container">
                {geoJson ? (
                  <MilanMap
                    geoJson={geoJson}
                    hotspots={hotspots}
                    alertByGrid={alertByGrid}
                    topHotspot={topHotspot}
                    onOpenGrid={onOpenGrid}
                  />
                ) : (
                  <div className="map-loading">
                    Loading Milan grid...
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="alerts-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">
                  ALERT FEED
                </span>
                <h4>Network Alerts</h4>
              </div>

              <span className="alert-count">
                {filteredAlerts.length} alerts
              </span>
            </div>

            <div className="activity-table-wrapper">
              <table className="activity-table">
                <thead>
                  <tr>
                    <th>Grid</th>
                    <th>Severity</th>
                    <th>Alert</th>
                    <th>Activity</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>

                <tbody>
                  {filteredAlerts.slice(0, Number(limit)).map(
                    (alert) => (
                      <tr
                        key={`${alert.grid_id}-${alert.timestamp}-${alert.status}`}
                        onClick={() =>
                          onOpenGrid(alert.grid_id)
                        }
                      >
                        <td>
                          <strong>{alert.grid_id}</strong>
                        </td>

                        <td>
                          <StatusBadge
                            status={
                              alert.severity === "HIGH"
                                ? "HIGH"
                                : alert.severity === "MEDIUM"
                                ? "ATTENTION"
                                : "NORMAL"
                            }
                          />
                        </td>

                        <td>{alert.status}</td>

                        <td>{formatActivity(alert.total_activity)}</td>

                        <td>{alert.timestamp}</td>
                      </tr>
                    )
                  )}

                  {filteredAlerts.length === 0 && (
                    <tr>
                      <td
                        colSpan="5"
                        className="empty-table"
                      >
                        No alerts match the selected
                        severity.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const symbols = {
    HIGH: "▲",
    ATTENTION: "◆",
    NORMAL: "●",
  };

  return (
    <span
      className={`status-badge status-${status.toLowerCase()}`}
    >
      <span className="status-symbol">
        {symbols[status]}
      </span>
      {status}
    </span>
  );
}

function MilanMap({
  geoJson,
  hotspots,
  alertByGrid,
  topHotspot,
  onOpenGrid,
}) {
  const hotspotGridIds = new Set(
    hotspots.map((item) => String(item.grid_id))
  );

  const getStatus = (gridId) => {
    const alert = alertByGrid.get(String(gridId));

    if (alert?.severity === "HIGH") {
      return "HIGH";
    }

    if (alert?.severity === "MEDIUM") {
      return "ATTENTION";
    }

    if (hotspotGridIds.has(String(gridId))) {
      return "ATTENTION";
    }

    return "NORMAL";
  };

  const getStyle = (feature) => {
    const gridId = String(feature.properties.cellId);
    const status = getStatus(gridId);

    const isTop =
      String(gridId) === String(topHotspot?.grid_id);

    if (status === "HIGH") {
      return {
        weight: isTop ? 4 : 2,
        opacity: 1,
        fillOpacity: 0.65,
        dashArray: "2 4",
      };
    }

    if (status === "ATTENTION") {
      return {
        weight: isTop ? 4 : 1.5,
        opacity: 1,
        fillOpacity: 0.45,
        dashArray: "8 5",
      };
    }

    return {
      weight: 0.7,
      opacity: 0.65,
      fillOpacity: 0.15,
      dashArray: null,
    };
  };

  const getFeatureColor = (feature) => {
    const gridId = String(feature.properties.cellId);
    const status = getStatus(gridId);

    if (status === "HIGH") {
      return "#ff4d5a";
    }

    if (status === "ATTENTION") {
      return "#f5b942";
    }

    return "#3d7894";
  };

  const onEachFeature = (feature, layer) => {
    const gridId = String(feature.properties.cellId);
    const status = getStatus(gridId);

    const hotspot = hotspots.find(
      (item) => String(item.grid_id) === gridId
    );

    layer.setStyle({
      ...getStyle(feature),
      color: getFeatureColor(feature),
      fillColor: getFeatureColor(feature),
    });

    layer.bindTooltip(
      `GRID ${gridId} • ${status}`,
      {
        sticky: true,
      }
    );

    layer.bindPopup(`
      <strong>Grid ${gridId}</strong><br/>
      Status: ${status}<br/>
      ${
        hotspot
          ? `Activity: ${formatActivity(hotspot.total_activity)}<br/>
             Time: ${hotspot.timestamp}`
          : "No ranked hotspot activity."
      }
    `);

    layer.on({
      click: () => onOpenGrid(gridId),
    });
  };

  return (
    <MapContainer
      className="milan-map"
      center={[45.4642, 9.19]}
      zoom={11}
      scrollWheelZoom={true}
      preferCanvas={true}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <GeoJSON
        data={geoJson}
        style={getStyle}
        onEachFeature={onEachFeature}
      />
    </MapContainer>
  );
}

function RiskPage() {
  const [form, setForm] = useState({
    grid_id: "4857",
    feature_timestamp: "2013-11-07T23:00:00",
    avg_activity: "0",
    activity_growth: "0",
    active_hours: "0",
    peak_ratio: "0",
    variability: "0",
    internet_share: "0",
  });

  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const updateField = (field, value) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const submitPrediction = async (event) => {
    event.preventDefault();

    setLoading(true);
    setError("");
    setPrediction(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/network/predict-risk`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            grid_id: form.grid_id,
            feature_timestamp: form.feature_timestamp,
            avg_activity: Number(form.avg_activity),
            activity_growth: Number(form.activity_growth),
            active_hours: Number(form.active_hours),
            peak_ratio: Number(form.peak_ratio),
            variability: Number(form.variability),
            internet_share: Number(form.internet_share),
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail
            ? JSON.stringify(data.detail)
            : "Prediction request failed."
        );
      }

      setPrediction(data);
    } catch (err) {
      setError(err.message || "Unable to reach prediction service.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="page-section">
      <div className="page-heading">
        <div>
          <span className="eyebrow">RE5 · PREDICTIVE ANALYTICS</span>
          <h1>Predictive Risk</h1>
          <p>
            Submit network features to the prediction service and inspect
            the returned model output.
          </p>
        </div>
      </div>

      <div className="risk-layout">
        <div className="panel risk-input-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">PREDICTION INPUT</span>
              <h2>Feature values</h2>
            </div>
            <span className="panel-icon">◎</span>
          </div>

          <form onSubmit={submitPrediction} className="risk-form">
            <div className="form-grid">
              <label className="form-field">
                <span>Grid ID</span>
                <input
                  type="text"
                  value={form.grid_id}
                  onChange={(event) =>
                    updateField("grid_id", event.target.value)
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Feature timestamp</span>
                <input
                  type="text"
                  value={form.feature_timestamp}
                  onChange={(event) =>
                    updateField(
                      "feature_timestamp",
                      event.target.value
                    )
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Average activity</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.avg_activity}
                  onChange={(event) =>
                    updateField("avg_activity", event.target.value)
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Activity growth</span>
                <input
                  type="number"
                  step="any"
                  value={form.activity_growth}
                  onChange={(event) =>
                    updateField(
                      "activity_growth",
                      event.target.value
                    )
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Active hours</span>
                <input
                  type="number"
                  min="0"
                  max="24"
                  step="any"
                  value={form.active_hours}
                  onChange={(event) =>
                    updateField("active_hours", event.target.value)
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Peak ratio</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.peak_ratio}
                  onChange={(event) =>
                    updateField("peak_ratio", event.target.value)
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Variability</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={form.variability}
                  onChange={(event) =>
                    updateField("variability", event.target.value)
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Internet share</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="any"
                  value={form.internet_share}
                  onChange={(event) =>
                    updateField(
                      "internet_share",
                      event.target.value
                    )
                  }
                  required
                />
              </label>
            </div>

            <div className="risk-form-footer">
              <span>
                POST /network/predict-risk
              </span>

              <button
                type="submit"
                className="primary-button"
                disabled={loading}
              >
                {loading ? "Running prediction..." : "Run prediction"}
              </button>
            </div>
          </form>

          {error && (
            <div className="error-banner">
              <strong>Prediction request failed</strong>
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="panel model-output-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">MODEL OUTPUT</span>
              <h2>Risk indicator</h2>
            </div>
            <span className="panel-icon">◆</span>
          </div>

          {prediction ? (
            <>
              <div className="risk-score-block">
                <span className="risk-score-label">Risk score</span>
                <strong className="risk-score">
                  {Number(prediction.risk_score).toFixed(2)}
                </strong>
              </div>

              <div className="risk-output-grid">
                <div className="output-item">
                  <span>Risk level</span>
                  <strong>{prediction.risk_level}</strong>
                </div>

                <div className="output-item">
                  <span>Model version</span>
                  <strong>{prediction.model_version}</strong>
                </div>
              </div>

              <div className="prediction-disclaimer">
                <span className="status-dot">●</span>
                <span>
                  This is a model-generated risk indicator, not a
                  confirmed network fault or congestion diagnosis.
                </span>
              </div>
            </>
          ) : (
            <div className="empty-risk-state">
              <div className="empty-risk-icon">◎</div>
              <h3>No prediction yet</h3>
              <p>
                Submit feature values to display the prediction
                service output.
              </p>
            </div>
          )}
        </div>

        <div className="panel explanation-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">EXPLANATION</span>
              <h2>Model interpretation</h2>
            </div>
            <span className="panel-icon">✦</span>
          </div>

          {prediction ? (
            <div className="explanation-content">
              <div className="explanation-note">
                <span>Prediction service note</span>
                <p>{prediction.explanation_note}</p>
              </div>

              <button
                type="button"
                className="secondary-button"
                disabled
                title="Reserved for the future Claude explanation phase"
              >
                Explain with AI
                <span>Coming later</span>
              </button>
            </div>
          ) : (
            <div className="empty-explanation">
              Explanation content will appear here after a
              prediction is returned.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function PlaceholderPage({
  title,
  description,
  endpoint,
}) {
  return (
    <div className="placeholder-card">
      <div className="placeholder-icon">◈</div>

      <p className="eyebrow">
        PHASE 5 MODULE
      </p>

      <h3>{title}</h3>

      <p>{description}</p>

      <div className="endpoint">
        Planned API
        <strong>{endpoint}</strong>
      </div>
    </div>
  );
}

export default App;
