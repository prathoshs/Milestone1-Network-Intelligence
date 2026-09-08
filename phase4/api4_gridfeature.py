from pathlib import Path
import sqlite3
from fastapi import HTTPException, APIRouter, Query
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
router = APIRouter()

# ============================================================
# API4 — GRID FEATURE ENDPOINT
# ============================================================
@router.get(
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
# ============================================================
# GRID TIMELINE + RISK RESPONSE
# ============================================================

class GridTimelineItem(BaseModel):
    timestamp: str
    sms_activity: float
    call_activity: float
    internet_activity: float
    total_activity: float
    risk_score: float | None
    risk_level: str | None
    model_version: str | None


class GridTimelineResponse(BaseModel):
    grid_id: str
    as_of: str
    points: list[GridTimelineItem]


# ============================================================
# GRID TIMELINE + RISK ENDPOINT
# ============================================================

@router.get(
    "/network/grid/{grid_id}/timeline",
    response_model=GridTimelineResponse,
    summary="Grid hourly activity and risk timeline",
)
def grid_timeline(
    grid_id: int,
    as_of: str | None = Query(
        default=None,
        description=(
            "Optional ISO-8601 reporting timestamp. "
            "Defaults to the latest available timestamp."
        ),
    ),
) -> GridTimelineResponse:

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

    conn = None

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # ----------------------------------------------------
        # Determine reporting timestamp
        # ----------------------------------------------------
        # if as_of is None:
        #     as_of_row = conn.execute(
        #         """
        #         SELECT MAX(event_time) AS max_timestamp
        #         FROM fact_network_activity
        #         WHERE grid_id = ?
        #         """,
        #         (str(grid_id),),
        #     ).fetchone()

        #     effective_as_of = (
        #     as_of_row["max_timestamp"].replace("T", " ")
        #     if as_of_row is not None
        #     and as_of_row["max_timestamp"]
        #     else None
        # )
        # else:
        #     effective_as_of = as_of.replace("Z", "").replace("T", " ")

        # if not effective_as_of:
        #     raise HTTPException(
        #         status_code=404,
        #         detail=f"No activity data found for grid {grid_id}",
        #     )

        # # ----------------------------------------------------
        # # Get the 24 hours ending at selected as_of
        # # ----------------------------------------------------
        # rows = conn.execute(
        #     """
        #     SELECT
        #         f.event_time AS timestamp,
        #         f.sms_count AS sms_activity,
        #         f.call_count AS call_activity,
        #         f.internet_volume AS internet_activity,
        #         (
        #             COALESCE(f.sms_count, 0)
        #             + COALESCE(f.call_count, 0)
        #             + COALESCE(f.internet_volume, 0)
        #         ) AS total_activity,

        #         r.risk_score,
        #         r.risk_level,
        #         r.model_version

        #     FROM fact_network_activity f

        #     LEFT JOIN network_risk_scores r
        #         ON CAST(r.grid_id AS TEXT) = CAST(f.grid_id AS TEXT)
        #         AND REPLACE(r.timestamp, 'T', ' ')
        #             = REPLACE(f.event_time, 'T', ' ')

        #     WHERE f.grid_id = ?
        #       AND f.event_time <= ?

        #     ORDER BY f.event_time DESC

        #     LIMIT 168
        #     """,
        #     (
        #         str(grid_id),
        #         effective_as_of,
        #     ),
        # ).fetchall()

        # if not rows:
        #     raise HTTPException(
        #         status_code=404,
        #         detail=(
        #             f"No activity data found for grid {grid_id} "
        #             f"at or before {as_of}"
        #         ),
        #     )
        
        if as_of is None:
            as_of_row = conn.execute(
                """
                SELECT MAX(event_time) AS max_timestamp
                FROM fact_network_activity
                WHERE grid_id = ?
                """,
                (str(grid_id),),
            ).fetchone()

            if (
                as_of_row is None
                or as_of_row["max_timestamp"] is None
            ):
                conn.close()
                raise HTTPException(
                    status_code=404,
                    detail=f"Grid {grid_id} not found.",
                )

            effective_as_of = as_of_row["max_timestamp"]

        else:
            effective_as_of = (
                as_of
                .replace("Z", "")
                .replace("T", " ")
            )

        rows = conn.execute(
            """
            SELECT
                f.event_time AS timestamp,
                f.sms_count AS sms_activity,
                f.call_count AS call_activity,
                f.internet_volume AS internet_activity,
                (
                    COALESCE(f.sms_count, 0)
                    + COALESCE(f.call_count, 0)
                    + COALESCE(f.internet_volume, 0)
                ) AS total_activity,
                r.risk_score,
                r.risk_level,
                r.model_version
            FROM fact_network_activity f
            LEFT JOIN network_risk_scores r
                ON CAST(r.grid_id AS TEXT) = CAST(f.grid_id AS TEXT)
                AND REPLACE(r.timestamp, 'T', ' ')
                    = REPLACE(f.event_time, 'T', ' ')
            WHERE f.grid_id = ?
            AND REPLACE(f.event_time, 'T', ' ') <= ?
            ORDER BY REPLACE(f.event_time, 'T', ' ') DESC
            LIMIT 168
            """,
            (
                str(grid_id),
                effective_as_of,
            ),
        ).fetchall()

        rows = list(reversed(rows))

        # ----------------------------------------------------
        # Return chronological order
        # ----------------------------------------------------
        rows = list(reversed(rows))

        points = []

        for row in rows:
            risk_score = (
                float(row["risk_score"])
                if row["risk_score"] is not None
                else None
            )

            points.append(
                GridTimelineItem(
                    timestamp=str(row["timestamp"]),
                    sms_activity=float(
                        row["sms_activity"] or 0
                    ),
                    call_activity=float(
                        row["call_activity"] or 0
                    ),
                    internet_activity=float(
                        row["internet_activity"] or 0
                    ),
                    total_activity=float(
                        row["total_activity"] or 0
                    ),
                    risk_score=risk_score,
                    risk_level=(
                        str(row["risk_level"])
                        if row["risk_level"] is not None
                        else None
                    ),
                    model_version=(
                        str(row["model_version"])
                        if row["model_version"] is not None
                        else None
                    ),
                )
            )

        return GridTimelineResponse(
            grid_id=str(grid_id),
            as_of=str(points[-1].timestamp),
            points=points,
        )

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse query failed: {exc}",
        ) from exc

    finally:
        if conn is not None:
            conn.close()