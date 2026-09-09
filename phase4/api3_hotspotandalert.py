from pathlib import Path
import csv
import sqlite3
from datetime import datetime

from fastapi import APIRouter,FastAPI, HTTPException, Query
from pydantic import BaseModel
# ============================================================
# CONFIGURATION
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = (
    BASE_DIR
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)
ALERT_FILE = (
    BASE_DIR
    / "phase1"
    / "output"
    / "network_alerts.csv"
)
# ============================================================
# PYDANTIC MODELS
# ============================================================
class HotspotItem(BaseModel):
    grid_id: str
    timestamp: str
    sms_activity: float
    call_activity: float
    internet_activity: float
    total_activity: float
    status: str
    reason: str
    risk_score: float | None = None
    risk_level: str | None = None
    model_version: str | None = None

class HotspotResponse(BaseModel):
    as_of: str
    limit: int
    results: list[HotspotItem]

class AlertItem(BaseModel):
    grid_id: str
    timestamp: str
    sms_activity: float
    call_activity: float
    internet_activity: float
    total_activity: float
    severity: str
    status: str
    reason: str
    risk_score: float | None = None
    risk_level: str | None = None
    model_version: str | None = None
    
class AlertResponse(BaseModel):
    as_of: str
    limit: int
    results: list[AlertItem]
# ============================================================
# FASTAPI APPLICATION
# ============================================================
router = APIRouter()
app = FastAPI(
    title="Milestone 1 Network Intelligence API",
    version="1.0.0",
)
app.include_router(router)
# ============================================================
# HELPERS
# ============================================================
def get_connection():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse database not found: {DB_PATH}",
        )
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse unavailable: {exc}",
        ) from exc
        
def load_anomaly_scores(conn, timestamp: str | None = None):
    try:
        if timestamp:
            rows = conn.execute(
                """
                SELECT
                    grid_id,
                    timestamp,
                    anomaly_score,
                    anomaly_direction
                FROM network_anomaly_scores
                WHERE timestamp = ?
                """,
                (timestamp,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    grid_id,
                    timestamp,
                    anomaly_score,
                    anomaly_direction
                FROM network_anomaly_scores
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return {}

    return {
        (str(row[0]), str(row[1])): {
            "anomaly_score": float(row[2]) if row[2] is not None else None,
            "anomaly_direction": str(row[3]) if row[3] is not None else None,
        }
        for row in rows
    }

def load_risk_scores(conn, timestamp: str | None = None):
    try:
        if timestamp:
            rows = conn.execute(
                """
                SELECT
                    grid_id,
                    timestamp,
                    risk_score,
                    risk_level,
                    model_version
                FROM network_risk_scores
                WHERE timestamp = ?
                """,
                (timestamp,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    grid_id,
                    timestamp,
                    risk_score,
                    risk_level,
                    model_version
                FROM network_risk_scores
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return {}

    return {
        (str(row[0]), str(row[1])): {
            "risk_score": float(row[2]),
            "risk_level": str(row[3]),
            "model_version": str(row[4]),
        }
        for row in rows
    }
        
def get_effective_as_of(conn, as_of: str | None) -> str:
    if as_of is None:
        row = conn.execute(
            """
            SELECT MAX(event_time) AS as_of
            FROM fact_network_activity
            """
        ).fetchone()

        if row is None or row["as_of"] is None:
            raise HTTPException(
                status_code=500,
                detail="Analytics layer contains no timestamps",
            )

        return row["as_of"]
    try:
        return datetime.fromisoformat(as_of).isoformat(
            timespec="seconds"
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid as_of. Use ISO-8601 format.",
        ) from exc

def severity_from_alert_type(alert_type: str) -> str:
    mapping = {
        "HIGH_ACTIVITY": "HIGH",
        "ACTIVITY_SPIKE": "MEDIUM",
        "ACTIVITY_DROP": "LOW",
    }
    return mapping.get(alert_type, "LOW")

def load_alerts():
    if not ALERT_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=f"NP3 alert output not found: {ALERT_FILE}",
        )
    try:
        with ALERT_FILE.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as file:
            return list(csv.DictReader(file))
    except (OSError, csv.Error) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"NP3 alert data unavailable: {exc}",
        ) from exc
# ============================================================
# API3 — HOTSPOTS
# ============================================================
@router.get(
    "/network/hotspots",
    response_model=HotspotResponse,
    summary="Current high-activity areas",
)
def hotspots(
    limit: int = Query(
        default=10,
        ge=1,
        le=10000,
        description="Maximum number of hotspot results.",
    ),
    severity: str | None = Query(
        default=None,
        description="Optional severity filter.",
    ),
    as_of: str | None = Query(
        default=None,
        description="Optional ISO-8601 reporting timestamp.",
    ),
) -> HotspotResponse:
    conn = get_connection()
    try:
        effective_as_of = get_effective_as_of(
            conn,
            as_of,
        )
        risk_scores = load_risk_scores(conn, effective_as_of)
        severity_filter = (
            severity.upper()
            if severity is not None
            else None
        )
        if severity_filter not in {
            None,
            "HIGH",
            "MEDIUM",
            "LOW",
        }:
            raise HTTPException(
                status_code=400,
                detail="Invalid severity. Use HIGH, MEDIUM or LOW.",
            )
        query = """
            SELECT
                grid_id,
                event_time AS timestamp,
                sms_count AS sms_activity,
                call_count AS call_activity,
                internet_volume AS internet_activity,
                (
                    sms_count +
                    call_count +
                    internet_volume
                ) AS total_activity
            FROM fact_network_activity
            WHERE event_time = ?
            ORDER BY total_activity DESC, grid_id ASC
            LIMIT ?
        """
        rows = conn.execute(
            query,
            (
                effective_as_of,
                limit,
            ),
        ).fetchall()
        results = []

        for row in rows:
            risk = risk_scores.get(
                (str(row["grid_id"]), str(row["timestamp"]))
            )

            total = float(row["total_activity"])
            results.append(
                HotspotItem(
                    grid_id=str(row["grid_id"]),
                    timestamp=row["timestamp"],
                    sms_activity=float(row["sms_activity"]),
                    call_activity=float(row["call_activity"]),
                    internet_activity=float(
                        row["internet_activity"]
                    ),
                    total_activity=total,
                    status="ACTIVE" if total > 0 else "NORMAL",
                    reason=(
                        "High total activity at the selected "
                        "reporting hour."
                    ),
                    risk_score=(
                        float(risk["risk_score"])
                        if risk is not None
                        else None
                    ),
                    risk_level=(
                        risk["risk_level"]
                        if risk is not None
                        else None
                    ),
                    model_version=(
                        risk["model_version"]
                        if risk is not None
                        else None
                    ),
                )
            )
        if severity_filter is not None:
            results = [
                item
                for item in results
                if (
                    severity_filter == "HIGH"
                    and item.total_activity > 0
                )
                or (
                    severity_filter == "MEDIUM"
                    and item.total_activity > 0
                )
                or (
                    severity_filter == "LOW"
                    and item.total_activity == 0
                )
            ]
        return HotspotResponse(
            as_of=effective_as_of,
            limit=limit,
            results=results[:limit],
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse query failed: {exc}",
        ) from exc
    finally:
        conn.close()
# ============================================================
# API3 — ALERTS
# ============================================================
@router.get(
    "/network/alerts",
    response_model=AlertResponse,
    summary="Latest network alert per grid",
)
def alerts(
    limit: int = Query(
        default=10000,
        ge=1,
        le=10000,
        description="Maximum number of grid alert results.",
    ),
    severity: str | None = Query(
        default=None,
        description="Optional severity filter.",
    ),
    as_of: str | None = Query(
        default=None,
        description="Optional ISO-8601 reporting timestamp.",
    ),
) -> AlertResponse:
    conn = get_connection()
    try:
        effective_as_of = get_effective_as_of(
            conn,
            as_of,
        )
        risk_scores = load_risk_scores(conn, effective_as_of)
        severity_filter = (
            severity.upper()
            if severity is not None
            else None
        )
        if severity_filter not in {
            None,
            "HIGH",
            "MEDIUM",
            "LOW",
        }:
            raise HTTPException(
                status_code=400,
                detail="Invalid severity. Use HIGH, MEDIUM or LOW.",
            )
        alert_rows = load_alerts()
        # Keep only the latest alert for each grid
        # at or before the reporting timestamp.
        latest_by_grid = {}
        for row in alert_rows:
            try:
                timestamp = datetime.fromisoformat(
                    row["timestamp"]
                ).isoformat(timespec="seconds")
            except (ValueError, TypeError):
                continue
            if timestamp > effective_as_of:
                continue
            grid_id = str(row["grid_id"])
            current = latest_by_grid.get(grid_id)
            if (
                current is None
                or timestamp > current["timestamp"]
            ):
                latest_by_grid[grid_id] = {
                    "grid_id": grid_id,
                    "timestamp": timestamp,
                    "alert_type": row["alert_type"],
                    "current_activity": float(
                        row["current_activity"]
                    ),
                    "baseline_activity": float(
                        row["baseline_activity"]
                    ),
                    "reason": row["reason"],
                }
        selected = []
        for row in latest_by_grid.values():
            risk = risk_scores.get(
                    (str(row["grid_id"]), str(row["timestamp"]))
                    )
            row_severity = severity_from_alert_type(
                row["alert_type"]
            )
            if (
                severity_filter is not None
                and row_severity != severity_filter
            ):
                continue
            
            selected.append(
                AlertItem(
                    grid_id=row["grid_id"],
                    timestamp=row["timestamp"],
                    sms_activity=0.0,
                    call_activity=0.0,
                    internet_activity=0.0,
                    total_activity=row["current_activity"],
                    severity=row_severity,
                    status=row["alert_type"],
                    reason=row["reason"],
                    risk_score=risk["risk_score"] if risk else None,
                    risk_level=risk["risk_level"] if risk else None,
                    model_version=risk["model_version"] if risk else None,
                )
            )

        selected.sort(
            key=lambda item: (
                item.severity,
                item.timestamp,
                item.grid_id,
            ),
            reverse=True,
        )

        return AlertResponse(
            as_of=effective_as_of,
            limit=limit,
            results=selected[:limit],
        )

    finally:
        conn.close()