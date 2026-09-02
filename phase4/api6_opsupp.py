from pathlib import Path
import json
import sqlite3
from datetime import datetime
from fastapi import APIRouter,FastAPI, HTTPException
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
STATUS_FILE = (
    BASE_DIR
    / "phase3"
    / "endtoend_orchestration_output"
    / "pipeline_status.json"
)
# ============================================================
# PYDANTIC MODELS
# ============================================================
class PipelineStatusResponse(BaseModel):
    last_run_id: str
    last_run_timestamp: str
    task_status: dict[str, str]
    rows_in: int
    rows_rejected: int
    nulls_handled: int
    rows_published: int
    as_of: str
    freshness: str
    healthy: bool
    reasons: list[str]

class GridLocationResponse(BaseModel):
    grid_id: str
    centroid_latitude: float
    centroid_longitude: float
    polygon_reference: str
# ============================================================
# FASTAPI APPLICATION
# ============================================================
router = APIRouter()

app = FastAPI(
    title="Milestone 1 Network Intelligence API",
    version="1.0.0",
)

app.include_router(router)

def build_task_status(status: dict) -> dict[str, str]:
    """
    Build per-task status from the DE7 pipeline status record.
    """
    pipeline_state = str(
        status.get("status", "UNKNOWN")
    ).upper()
    quality_state = str(
        status.get("quality_check", "UNKNOWN")
    ).upper()
    checks = status.get("checks", {})
    failed_task = status.get("failed_task")
    # Failed pipeline
    task_status = {
        "ingest": "UNKNOWN",
        "validate": "UNKNOWN",
        "spark_process": "UNKNOWN",
        "load_warehouse": "UNKNOWN",
        "quality_check": "UNKNOWN",
        "notify": "UNKNOWN",
    }
     # Default successful pipeline
    if pipeline_state == "SUCCESS" and quality_state == "PASS":
        return {
            "ingest": "SUCCESS",                "validate": "SUCCESS",
            "spark_process": "SUCCESS",
            "load_warehouse": "SUCCESS",
            "quality_check": "SUCCESS",
            "notify": "SUCCESS",
        }

    if failed_task:
        task_status[str(failed_task)] = "FAILED"
    # Use available quality checks as supporting evidence
    if checks.get("processed_activity_exists"):
        task_status["spark_process"] = "SUCCESS"
    if checks.get("hourly_summary_exists"):
        task_status["spark_process"] = "SUCCESS"
    if checks.get("dashboard_summary_exists"):
        task_status["spark_process"] = "SUCCESS"
    if checks.get("warehouse_exists"):
        task_status["load_warehouse"] = "SUCCESS"
    if quality_state == "PASS":
        task_status["quality_check"] = "SUCCESS"
    elif quality_state == "FAIL":
        task_status["quality_check"] = "FAILED"
    return task_status
# ============================================================
# API6 — PIPELINE STATUS
# ============================================================
@router.get(
    "/pipeline/status",
    response_model=PipelineStatusResponse,
    summary="Pipeline health and status",
)
def pipeline_status() -> PipelineStatusResponse:
    if not STATUS_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Pipeline status record not found: {STATUS_FILE}",
        )
    try:
        with STATUS_FILE.open("r", encoding="utf-8") as file:
            status = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to read pipeline status: {exc}",
        ) from exc
    pipeline_state = str(status.get("status", "UNKNOWN")).upper()
    quality_state = str(status.get("quality_check", "UNKNOWN")).upper()
    healthy = (
        pipeline_state == "SUCCESS"
        and quality_state == "PASS"
    )
    reasons = []
    if pipeline_state != "SUCCESS":
        reasons.append(
            f"Pipeline status is {pipeline_state}"
        )
    if quality_state != "PASS":
        reasons.append(
            f"Quality check status is {quality_state}"
        )
    failed_task = status.get("failed_task")
    if failed_task:
        reasons.append(
            f"Failed task: {failed_task}"
        )
    # --------------------------------------------------------
    # Current analytics AS_OF
    # --------------------------------------------------------
    analytics_as_of = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                """
                SELECT MAX(event_time) AS as_of
                FROM fact_network_activity
                """
            ).fetchone()
            analytics_as_of = row[0]
        except sqlite3.Error:
            analytics_as_of = None
        finally:
            conn.close()
    if analytics_as_of is None:
        analytics_as_of = str(status.get("as_of", "UNKNOWN"))
    # --------------------------------------------------------
    # Freshness
    # --------------------------------------------------------
    freshness = "UNKNOWN"
    try:
        as_of_dt = datetime.fromisoformat(
            analytics_as_of
        )
        age_hours = (
            datetime.now() - as_of_dt
        ).total_seconds() / 3600
        if age_hours <= 24:
            freshness = "FRESH"
        elif age_hours <= 72:
            freshness = "STALE"
        else:
            freshness = "VERY_STALE"
    except (ValueError, TypeError):
        freshness = "UNKNOWN"
    # --------------------------------------------------------
    # Return status
    # --------------------------------------------------------
    return PipelineStatusResponse(
        last_run_id=str(
            status.get("run_id", "UNKNOWN")
        ),
        last_run_timestamp=str(
            status.get("timestamp", "")
        ),
        task_status= build_task_status(status),
        rows_in=int(status.get("rows_in", 0)),
        rows_rejected=int(
            status.get("rows_rejected", 0)
        ),
        nulls_handled=int(
            status.get("nulls_handled", 0)
        ),
        rows_published=int(
            status.get("rows_published", 0)
        ),
        as_of=analytics_as_of,
        freshness=freshness,
        healthy=healthy,
        reasons=reasons,
    )
# ============================================================
# API6 — GRID LOCATION
# ============================================================
@router.get(
    "/network/grid/{grid_id}/location",
    response_model=GridLocationResponse,
    summary="Grid geographic location",
)
def grid_location(grid_id: int) -> GridLocationResponse:
    if not 1 <= grid_id <= 10000:
        raise HTTPException(
            status_code=404,
            detail=f"Grid {grid_id} not found",
        )
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse database not found: {DB_PATH}",
        )
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                grid_id,
                centroid_latitude,
                centroid_longitude,
                geometry_reference
            FROM dim_grid
            WHERE grid_id = ?
            """,
            (str(grid_id),),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Grid {grid_id} not found",
            )
        return GridLocationResponse(
            grid_id=str(row["grid_id"]),
            centroid_latitude=float(
                row["centroid_latitude"]
            ),
            centroid_longitude=float(
                row["centroid_longitude"]
            ),
            polygon_reference=str(
                row["geometry_reference"]
            ),
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse query failed: {exc}",
        ) from exc
    finally:
        conn.close()