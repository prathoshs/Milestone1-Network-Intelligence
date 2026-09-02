from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException
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
# PYDANTIC RESPONSE MODEL
# ============================================================
class GridFeatureResponse(BaseModel):
    grid_id: str
    feature_timestamp: str
    avg_activity: float
    activity_growth: float
    active_hours: float
    peak_ratio: float
    variability: float
    internet_share: float
    data_quality: str
    freshness: str

# ============================================================
# FASTAPI APPLICATION
# ============================================================
app = FastAPI(
    title="Milestone 1 Network Intelligence API",
    version="1.0.0",
)

# ============================================================
# API4 — GRID FEATURE ENDPOINT
# ============================================================
@app.get(
    "/network/grid/{grid_id}/features",
    response_model=GridFeatureResponse,
    summary="Grid ML feature vector",
)
def grid_features(grid_id: int) -> GridFeatureResponse:
    # --------------------------------------------------------
    # Grid ID validation
    # --------------------------------------------------------
    if not 1 <= grid_id <= 10000:
        raise HTTPException(
            status_code=404,
            detail=f"Grid {grid_id} not found",
        )
    # --------------------------------------------------------
    # Database validation
    # --------------------------------------------------------
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse database not found: {DB_PATH}",
        )
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # ----------------------------------------------------
        # Check that ML2 feature table exists
        # ----------------------------------------------------
        table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'network_feature_table'
            """
        ).fetchone()
        if table is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "ML feature table unavailable: "
                    "network_feature_table has not been created yet."
                ),
            )
        # ----------------------------------------------------
        # Read stored ML features
        # NO FEATURE CALCULATION HERE
        # ----------------------------------------------------
        row = conn.execute(
            """
            SELECT
                grid_id,
                feature_timestamp,
                avg_activity,
                activity_growth,
                active_hours,
                peak_ratio,
                variability,
                internet_share
            FROM network_feature_table
            WHERE grid_id = ?
            ORDER BY feature_timestamp DESC
            LIMIT 1
            """,
            (str(grid_id),),
        ).fetchone()
        # ----------------------------------------------------
        # No stored features
        # ----------------------------------------------------
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"No stored features found for grid {grid_id}",
            )
        # ----------------------------------------------------
        # Freshness / quality metadata
        # ----------------------------------------------------
        feature_timestamp = row["feature_timestamp"]
        return GridFeatureResponse(
            grid_id=str(row["grid_id"]),
            feature_timestamp=feature_timestamp,
            avg_activity=float(row["avg_activity"]),
            activity_growth=float(row["activity_growth"]),
            active_hours=float(row["active_hours"]),
            peak_ratio=float(row["peak_ratio"]),
            variability=float(row["variability"]),
            internet_share=float(row["internet_share"]),
            data_quality="STORED",
            freshness="AVAILABLE",
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse query failed: {exc}",
        ) from exc
    finally:
        conn.close()