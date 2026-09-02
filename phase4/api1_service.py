from datetime import datetime
from pathlib import Path
import sqlite3
from phase4.api1_models import NetworkSummaryResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE_DB = PROJECT_ROOT / "phase3" / "warehouse_output" / "network_analytics.db"

def get_network_summary(
    requested_as_of: str | None = None,
) -> NetworkSummaryResponse:

    if not WAREHOUSE_DB.is_file():
        raise FileNotFoundError(
            f"Warehouse database not found: {WAREHOUSE_DB}"
        )
    connection = sqlite3.connect(
        f"file:{WAREHOUSE_DB}?mode=ro",
        uri=True,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    try:
        # Resolve AS_OF dynamically from the analytics layer.
        row = connection.execute(
            """
            SELECT MAX(event_time) AS max_event_time
            FROM fact_network_activity
            """
        ).fetchone()
        if row is None or row["max_event_time"] is None:
            raise RuntimeError(
                "Analytics layer contains no timestamps"
            )
        if requested_as_of is None:
            effective_as_of = row["max_event_time"]
        else:
            try:
                effective_as_of = datetime.fromisoformat(
                    requested_as_of
                ).isoformat(timespec="seconds")
            except ValueError as exc:
                raise ValueError(
                    "as_of must be a valid ISO-8601 timestamp"
                ) from exc
        # Ensure the requested AS_OF is available.
        available = connection.execute(
            """
            SELECT 1
            FROM fact_network_activity
            WHERE event_time <= ?
            LIMIT 1
            """,
            (effective_as_of,),
        ).fetchone()
        if available is None:
            raise ValueError(
                "Requested as_of is outside the available analytics data"
            )
        # Total activity + active grids.
        summary = connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        sms_count +
                        call_count +
                        internet_volume
                    ),
                    0.0
                ) AS total_activity,

                COUNT(
                    DISTINCT CASE
                        WHEN (
                            sms_count +
                            call_count +
                            internet_volume
                        ) > 0
                        THEN grid_id
                    END
                ) AS active_grids

            FROM fact_network_activity
            WHERE event_time <= ?
            """,
            (effective_as_of,),
        ).fetchone()
        # Peak hour.
        peak = connection.execute(
            """
            SELECT
                event_time,
                SUM(
                    sms_count +
                    call_count +
                    internet_volume
                ) AS total_activity
            FROM fact_network_activity
            WHERE event_time <= ?
            GROUP BY event_time
            ORDER BY total_activity DESC, event_time ASC
            LIMIT 1
            """,
            (effective_as_of,),
        ).fetchone()
        # Top grid.
        top_grid = connection.execute(
            """
            SELECT
                grid_id,
                SUM(
                    sms_count +
                    call_count +
                    internet_volume
                ) AS total_activity
            FROM fact_network_activity
            WHERE event_time <= ?
            GROUP BY grid_id
            ORDER BY total_activity DESC, grid_id ASC
            LIMIT 1
            """,
            (effective_as_of,),
        ).fetchone()

        if peak is None or top_grid is None:
            raise RuntimeError(
                "No analytics data available for the requested AS_OF"
            )

        return NetworkSummaryResponse(
            total_activity=float(summary["total_activity"]),
            active_grids=int(summary["active_grids"]),
            peak_hour=peak["event_time"],
            top_grid=str(top_grid["grid_id"]),
            as_of=effective_as_of,
        )

    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Warehouse query failed: {exc}"
        ) from exc

    finally:
        connection.close()
