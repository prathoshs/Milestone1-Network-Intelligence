from pathlib import Path
import sqlite3
from datetime import datetime
from fastapi import HTTPException, APIRouter, Query
from pydantic import BaseModel
import numpy as np

# Import NP3's shared activity floor constant
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase1"))
from np3_alert import FLOOR_PERCENTILE

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

class TopMoverItem(BaseModel):
    grid_id: str
    feature_timestamp: str
    avg_activity: float
    activity_growth: float
    anomaly_score: float | None = None
    anomaly_direction: str | None = None
    risk_score: float | None = None
    risk_level: str | None = None
    model_version: str | None = None

class TopMoversResponse(BaseModel):
    as_of: str
    limit: int
    activity_floor: float
    results: list[TopMoverItem]

# ============================================================
# FASTAPI APPLICATION
# ============================================================
router = APIRouter()

# ============================================================
# SHARED HELPERS (reused from api3_hotspotandalert.py)
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

def load_risk_scores(conn):
    try:
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

def load_anomaly_scores(conn):
    try:
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

# ============================================================
# API4 — TOP MOVERS (activity growth ranking)
# ============================================================

@router.get(
    "/network/top-movers",
    response_model=TopMoversResponse,
    summary="Top grids by sharpest activity increase vs baseline",
)
def top_movers(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of top-mover results.",
    ),
    as_of: str | None = Query(
        default=None,
        description="Optional ISO-8601 reporting timestamp.",
    ),
) -> TopMoversResponse:
    conn = get_connection()
    try:
        effective_as_of = get_effective_as_of(conn, as_of)
        risk_scores = load_risk_scores(conn)
        anomaly_scores = load_anomaly_scores(conn)

        # Normalize effective_as_of to space-separated format
        # to match network_feature_table.feature_timestamp storage
        normalized_as_of = effective_as_of.replace("T", " ")

        # Fetch all feature rows for the reporting hour
        query = """
            SELECT
                grid_id,
                feature_timestamp,
                avg_activity,
                activity_growth
            FROM network_feature_table
            WHERE REPLACE(feature_timestamp, 'T', ' ') = ?
            ORDER BY activity_growth DESC
        """

        rows = conn.execute(
            query,
            (normalized_as_of,),
        ).fetchall()

        if not rows:
            return TopMoversResponse(
                as_of=effective_as_of,
                limit=limit,
                activity_floor=0.0,
                results=[],
            )

        # Extract avg_activity values and compute floor (NP3-derived)
        avg_activities = [
            float(row["avg_activity"])
            for row in rows
        ]
        activity_floor = float(
            np.quantile(
                avg_activities,
                FLOOR_PERCENTILE,
            )
        )

        # Filter: keep only rows above the activity floor
        filtered_rows = [
            row
            for row in rows
            if float(row["avg_activity"]) >= activity_floor
        ]

        # Sort by activity_growth descending (already done by SQL, but
        # ensure ordering after filter)
        filtered_rows = sorted(
            filtered_rows,
            key=lambda r: float(r["activity_growth"]),
            reverse=True,
        )

        # Limit to the requested count
        limited_rows = filtered_rows[:limit]

        results = []
        for row in limited_rows:
            grid_id_str = str(row["grid_id"])
            timestamp_str = str(row["feature_timestamp"])

            # Look up risk and anomaly scores
            risk = risk_scores.get(
                (grid_id_str, timestamp_str)
            )
            anomaly = anomaly_scores.get(
                (grid_id_str, timestamp_str)
            )

            results.append(
                TopMoverItem(
                    grid_id=grid_id_str,
                    feature_timestamp=timestamp_str,
                    avg_activity=float(row["avg_activity"]),
                    activity_growth=float(row["activity_growth"]),
                    anomaly_score=(
                        anomaly["anomaly_score"]
                        if anomaly is not None
                        else None
                    ),
                    anomaly_direction=(
                        anomaly["anomaly_direction"]
                        if anomaly is not None
                        else None
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

        return TopMoversResponse(
            as_of=effective_as_of,
            limit=limit,
            activity_floor=activity_floor,
            results=results,
        )

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Warehouse query failed: {exc}",
        ) from exc
    finally:
        conn.close()