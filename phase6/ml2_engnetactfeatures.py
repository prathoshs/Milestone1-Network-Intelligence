"""
ML2 - Network Activity Feature Engineering

Features are calculated strictly from data available through
feature_timestamp = t.

Prediction target:
    future interval t+1

Feature window:
    trailing 24 hourly intervals ending at t

Baseline window:
    preceding 24 hourly intervals immediately before the
    feature window.

IMPORTANT:
    This module owns feature engineering.
    API4 must only read network_feature_table.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path
from typing import Iterable
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DB_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)

TABLE_NAME = "network_feature_table"

RECENT_HOURS = 24
BASELINE_HOURS = 24

FEATURE_COLUMNS = [
    "avg_activity",
    "activity_growth",
    "peak_ratio",
    "variability",
    "internet_share",
    "current_activity",
    "previous_hour_activity",
    "rolling_3h_activity",
    "rolling_6h_activity",
    "rolling_24h_activity",
    "activity_change",
    "activity_change_pct",
]

def _get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()
    if not rows:
        raise RuntimeError(
            f"Required table does not exist: {table}"
        )
    return [row[1] for row in rows]

def _resolve_column(
    columns: Iterable[str],
    candidates: list[str],
    logical_name: str,
) -> str:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise RuntimeError(
        f"Could not find {logical_name} column. "
        f"Tried {candidates}. "
        f"Available columns: {sorted(available)}"
    )

def load_hourly_activity(db_path: Path = DB_PATH) -> pd.DataFrame:
    """
    Load hourly grid activity from the Phase 3 warehouse.

    Actual Phase 3 fact schema:
        sms_count
        call_count
        internet_volume

    ML2 derives:
        total_activity = sms_count + call_count + internet_volume
        internet_activity = internet_volume
    """

    if not db_path.exists():
        raise FileNotFoundError(
            f"Warehouse database not found: {db_path}"
        )

    conn = sqlite3.connect(db_path)

    try:
        query = """
            SELECT
                CAST(grid_id AS TEXT) AS grid_id,
                event_time AS timestamp,
                (
                    COALESCE(sms_count, 0)
                    + COALESCE(call_count, 0)
                    + COALESCE(internet_volume, 0)
                ) AS total_activity,
                COALESCE(internet_volume, 0) AS internet_activity
            FROM fact_network_activity
            ORDER BY grid_id, event_time
        """

        df = pd.read_sql_query(query, conn)

    finally:
        conn.close()

    if df.empty:
        raise RuntimeError(
            "fact_network_activity contains no rows."
        )

    df["grid_id"] = df["grid_id"].astype(str)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    df["total_activity"] = pd.to_numeric(
        df["total_activity"],
        errors="coerce",
    ).fillna(0.0)

    df["internet_activity"] = pd.to_numeric(
        df["internet_activity"],
        errors="coerce",
    ).fillna(0.0)

    df = df.dropna(subset=["timestamp"])

    duplicate_mask = df.duplicated(
        subset=["grid_id", "timestamp"],
        keep=False,
    )

    if duplicate_mask.any():
        duplicate_count = int(duplicate_mask.sum())

        raise RuntimeError(
            "Duplicate grid/hour records detected in "
            f"fact_network_activity: {duplicate_count} rows."
        )

    return (
        df.sort_values(["grid_id", "timestamp"])
        .reset_index(drop=True)
    )

def safe_ratio(
    numerator: float,
    denominator: float,
) -> float:
    """
    Explicitly handle division by zero.

    A zero denominator produces 0.0 rather than NaN or infinity.
    """
    if denominator == 0 or not math.isfinite(denominator):
        return 0.0
    value = numerator / denominator
    if not math.isfinite(value):
        return 0.0
    return float(value)

def calculate_features_for_grid(
    grid_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate ML2 features for one grid.

    For each feature_timestamp t:

        recent window  = t-23h ... t
        baseline       = t-47h ... t-24h

    No observation after t is accessed.
    """
    grid_df = (
        grid_df
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    records = []
    for i in range(len(grid_df)):
        feature_timestamp = grid_df.loc[i, "timestamp"]
        # Need 24 recent observations and 24 baseline observations.
        if i < (RECENT_HOURS + BASELINE_HOURS - 1):
            continue
        recent = grid_df.iloc[
            i - RECENT_HOURS + 1 : i + 1
        ]
        baseline = grid_df.iloc[
            i - RECENT_HOURS - BASELINE_HOURS + 1 :
            i - RECENT_HOURS + 1
        ]
        # Defensive timestamp check.
        if recent["timestamp"].max() > feature_timestamp:
            raise AssertionError(
                "LEAKAGE: recent feature window contains "
                "data after feature_timestamp."
            )
        if baseline["timestamp"].max() > feature_timestamp:
            raise AssertionError(
                "LEAKAGE: baseline feature window contains "
                "data after feature_timestamp."
            )
        activity = recent["total_activity"].astype(float)
        internet = recent["internet_activity"].astype(float)
        avg_activity = float(activity.mean())
        peak_activity = float(activity.max())
        active_hours = int(
            (activity > 0).sum()
        )
        variability = float(
            activity.std(ddof=0)
        )
        peak_ratio = safe_ratio(
            peak_activity,
            avg_activity,
        )
        total_recent_activity = float(
            activity.sum()
        )
        total_internet_activity = float(
            internet.sum()
        )
        internet_share = safe_ratio(
            total_internet_activity,
            total_recent_activity,
        )
        baseline_avg = float(
            baseline["total_activity"]
            .astype(float)
            .mean()
        )
        activity_growth = safe_ratio(
            avg_activity - baseline_avg,
            baseline_avg,
        )
        record = {
            "grid_id": str(grid_df.loc[i, "grid_id"]),
            "feature_timestamp": feature_timestamp.isoformat(),
            "avg_activity": avg_activity,
            "activity_growth": activity_growth,
            "active_hours": active_hours,
            "peak_ratio": peak_ratio,
            "variability": variability,
            "internet_share": internet_share,
        }
        records.append(record)
    return pd.DataFrame(records)

def build_feature_table(
    activity_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the complete network feature table.
    """
    feature_frames = []
    for grid_id, grid_df in activity_df.groupby(
        "grid_id",
        sort=True,
    ):
        features = calculate_features_for_grid(
            grid_df
        )
        if not features.empty:
            feature_frames.append(features)
    if not feature_frames:
        raise RuntimeError(
            "No feature rows could be generated. "
            "The available history may be too short."
        )
    result = pd.concat(
        feature_frames,
        ignore_index=True,
    )
    result["feature_timestamp"] = pd.to_datetime(
        result["feature_timestamp"]
    ).dt.strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    # Exact ML2 feature contract.
    expected_columns = [
        "grid_id",
        "feature_timestamp",
        *FEATURE_COLUMNS,
    ]
    result = result[expected_columns]
    # Final finite-value protection.
    for column in FEATURE_COLUMNS:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        ).fillna(0.0)
        result[column] = result[column].replace(
            [float("inf"), float("-inf")],
            0.0,
        )
    # Explicit range safety.
    result["active_hours"] = (
        result["active_hours"]
        .clip(lower=0, upper=24)
        .astype(int)
    )
    result["internet_share"] = (
        result["internet_share"]
        .clip(lower=0.0, upper=1.0)
    )
    return result.sort_values(
        ["grid_id", "feature_timestamp"]
    ).reset_index(drop=True)

def persist_feature_table(
    features: pd.DataFrame,
    db_path: Path = DB_PATH,
) -> None:
    """
    Persist the ML2 feature table into the Phase 3 warehouse.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"DROP TABLE IF EXISTS {TABLE_NAME}"
        )
        features.to_sql(
            TABLE_NAME,
            conn,
            if_exists="replace",
            index=False,
        )
        conn.execute(
            f"""
            CREATE UNIQUE INDEX
            IF NOT EXISTS idx_network_feature_grid_time
            ON {TABLE_NAME}
            (grid_id, feature_timestamp)
            """
        )
        conn.execute(
            f"""
            CREATE INDEX
            IF NOT EXISTS idx_network_feature_timestamp
            ON {TABLE_NAME}
            (feature_timestamp)
            """
        )
        conn.commit()
    finally:
        conn.close()

def run(db_path: Path = DB_PATH) -> pd.DataFrame:
    """
    Complete ML2 feature-engineering run.
    """
    print("=" * 70)
    print("ML2 - Network Activity Feature Engineering")
    print("=" * 70)
    print(f"Warehouse: {db_path}")
    print(
        f"Recent window: {RECENT_HOURS} hours ending at t"
    )
    print(
        f"Baseline window: {BASELINE_HOURS} hours before recent window"
    )
    activity = load_hourly_activity(db_path)
    print(
        f"Source rows: {len(activity):,}"
    )
    print(
        "Source timestamp range:",
        activity["timestamp"].min(),
        "to",
        activity["timestamp"].max(),
    )
    features = build_feature_table(activity)
    persist_feature_table(
        features,
        db_path,
    )
    print(
        f"Feature rows written: {len(features):,}"
    )
    print(
        "Feature timestamp range:",
        features["feature_timestamp"].min(),
        "to",
        features["feature_timestamp"].max(),
    )
    print()
    print("Feature columns:")
    for column in [
        "grid_id",
        "feature_timestamp",
        *FEATURE_COLUMNS,
    ]:
        print(f"  - {column}")
    print()
    print("ML2 feature table created successfully.")

    return features

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to network_analytics.db",
    )

    args = parser.parse_args()
    run(args.db)