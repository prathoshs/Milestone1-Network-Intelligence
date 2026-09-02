from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from fastapi import APIRouter,FastAPI, HTTPException, Query
from pydantic import BaseModel
# ============================================================
# CONFIGURATION
# ============================================================
DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)
# ============================================================
# PYDANTIC RESPONSE MODELS #models
# ============================================================
class GridActivityPoint(BaseModel):
    timestamp: str
    sms_activity: float
    call_activity: float
    internet_activity: float
    total_activity: float
    
class GridActivityResponse(BaseModel):
    grid_id: str
    as_of: str
    points: list[GridActivityPoint]
# ============================================================
# FASTAPI APPLICATION
# ============================================================
#main
router = APIRouter()
app = FastAPI(
    title="Milestone 1 Network Intelligence API",
    version="1.0.0",
)
app.include_router(router)
# ============================================================
# API2 — GRID ACTIVITY DRILL-DOWN
# ============================================================
#router
@router.get(
    "/network/grid/{grid_id}",
    response_model=GridActivityResponse,
    summary="Grid activity drill-down",
)
def grid_activity(
    grid_id: int,
    date: str | None = Query(
        default=None,
        description="Optional date in YYYY-MM-DD format.",
    ),
    hour: int | None = Query(
        default=None,
        ge=0,
        le=23,
        description="Optional hour from 0 to 23.",
    ),
    as_of: str | None = Query(
        default=None,
        description="Optional ISO-8601 reporting timestamp.",
    ),
) -> GridActivityResponse:
    # --------------------------------------------------------
    # Grid ID validation
    # --------------------------------------------------------
#service
    if not 1 <= grid_id <= 10000:
        raise HTTPException(
            status_code=404,
            detail=f"Grid {grid_id} not found",
        )
    # --------------------------------------------------------
    # Connect to warehouse
    # --------------------------------------------------------
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse database not found: {DB_PATH}",
        )
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse unavailable: {exc}",
        ) from exc
    try:
        # ----------------------------------------------------
        # Determine effective AS_OF
        # ----------------------------------------------------
        if as_of is None:
            row = conn.execute(
                """
                SELECT MAX(event_time) AS as_of
                FROM fact_network_activity
                """
            ).fetchone()
            effective_as_of = row["as_of"]
            if effective_as_of is None:
                raise HTTPException(
                    status_code=500,
                    detail="Analytics layer contains no timestamps",
                )
        else:
            try:
                effective_as_of = datetime.fromisoformat(
                    as_of
                ).isoformat(timespec="seconds")
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid as_of. Use ISO-8601 format.",
                ) from exc
        # ----------------------------------------------------
        # Optional date + hour
        # ----------------------------------------------------
        if date is not None and hour is None:
            raise HTTPException(
                status_code=400,
                detail="hour is required when date is provided",
            )
        if hour is not None and date is None:
            raise HTTPException(
                status_code=400,
                detail="date is required when hour is provided",
            )
        if date is not None and hour is not None:
            try:
                effective_as_of = datetime.fromisoformat(
                    f"{date}T{hour:02d}:00:00"
                ).isoformat(timespec="seconds")
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date. Use YYYY-MM-DD format.",
                ) from exc
        # ----------------------------------------------------
        # Confirm grid exists
        # ----------------------------------------------------
        grid_exists = conn.execute(
            """
            SELECT 1
            FROM fact_network_activity
            WHERE grid_id = ?
            LIMIT 1
            """,
            (str(grid_id),),
        ).fetchone()
        if grid_exists is None:
            raise HTTPException(
                status_code=404,
                detail=f"Grid {grid_id} not found",
            )
        # ----------------------------------------------------
        # Trailing 24 hourly intervals
        # ----------------------------------------------------
        as_of_dt = datetime.fromisoformat(effective_as_of)
        window_start = (
            as_of_dt - timedelta(hours=23)
        ).isoformat(timespec="seconds")
        rows = conn.execute(
            """
            SELECT
                event_time,
                sms_count AS sms_activity,
                call_count AS call_activity,
                internet_volume AS internet_activity,
                (
                    sms_count +
                    call_count +
                    internet_volume
                ) AS total_activity
            FROM fact_network_activity
            WHERE grid_id = ?
              AND event_time BETWEEN ? AND ?
            ORDER BY event_time
            """,
            (
                str(grid_id),
                window_start,
                effective_as_of,
            ),
        ).fetchall()
        # ----------------------------------------------------
        # Build time-series response
        # ----------------------------------------------------
        points = [
            GridActivityPoint(
                timestamp=row["event_time"],
                sms_activity=row["sms_activity"],
                call_activity=row["call_activity"],
                internet_activity=row["internet_activity"],
                total_activity=row["total_activity"],
            )
            for row in rows
        ]
        return GridActivityResponse(
            grid_id=str(grid_id),
            as_of=effective_as_of,
            points=points,
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse query failed: {exc}",
        ) from exc
    finally:
        conn.close()