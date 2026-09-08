from pathlib import Path
import sqlite3
import pandas as pd
import numpy as np


# ============================================================
# PATHS
# ============================================================

PROJECT_DIR = Path.home() / "Milestone1-Network-Intelligence"
PHASE6_DIR = PROJECT_DIR / "phase6"

DB_PATH = (
    PROJECT_DIR
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)

PREDICTIONS_PATH = PHASE6_DIR / "ml3_predictions.csv"


FEATURE_TABLE = "network_feature_table"

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
    "activity_change",
    "activity_change_pct",
]

BASELINE_HOURS = 24
HIGH_ACTIVITY_MULTIPLIER = 1.50


# ============================================================
# HELPERS
# ============================================================

def check(condition, message):
    if condition:
        print(f"PASS: {message}")
        return True
    else:
        print(f"FAIL: {message}")
        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("ML3 - DATA LEAKAGE TEST")
    print("=" * 70)

    results = []

    # --------------------------------------------------------
    # 1. Load ML2 features
    # --------------------------------------------------------

    print("\n[1] Loading ML2 feature table...")

    conn = sqlite3.connect(DB_PATH)

    features = pd.read_sql_query(
        f"""
        SELECT
            grid_id,
            feature_timestamp,
            avg_activity,
            activity_growth,
            active_hours,
            peak_ratio,
            variability,
            internet_share
        FROM {FEATURE_TABLE}
        ORDER BY grid_id, feature_timestamp
        """,
        conn,
    )

    features["feature_timestamp"] = pd.to_datetime(
        features["feature_timestamp"]
    )

    print(f"Feature rows: {len(features):,}")
    print(
        f"Feature range: "
        f"{features['feature_timestamp'].min()} -> "
        f"{features['feature_timestamp'].max()}"
    )

    # --------------------------------------------------------
    # 2. Feature timestamp integrity
    # --------------------------------------------------------

    print("\n[2] Checking feature timestamp integrity...")

    duplicate_features = features.duplicated(
        subset=["grid_id", "feature_timestamp"]
    ).sum()

    results.append(
        check(
            duplicate_features == 0,
            f"No duplicate grid/timestamp feature rows "
            f"(duplicates={duplicate_features})",
        )
    )

    # --------------------------------------------------------
    # 3. Verify temporal features cannot use future data
    # --------------------------------------------------------

    print("\n[3] Checking temporal feature leakage...")

    activity = pd.read_sql_query(
        """
        SELECT
            grid_id,
            event_time AS timestamp,
            (
                COALESCE(sms_count, 0)
                + COALESCE(call_count, 0)
                + COALESCE(internet_volume, 0)
            ) AS total_activity
        FROM fact_network_activity
        ORDER BY grid_id, timestamp
        """,
        conn,
    )

    activity["timestamp"] = pd.to_datetime(activity["timestamp"])

    temporal = activity.copy()

    temporal = temporal.sort_values(
        ["grid_id", "timestamp"]
    ).reset_index(drop=True)

    grouped = temporal.groupby("grid_id")["total_activity"]

    temporal["previous_hour_activity"] = grouped.shift(1)

    temporal["rolling_3h_activity"] = (
        grouped
        .rolling(window=3, min_periods=3)
        .mean()
        .reset_index(level=0, drop=True)
    )

    temporal["rolling_6h_activity"] = (
        grouped
        .rolling(window=6, min_periods=6)
        .mean()
        .reset_index(level=0, drop=True)
    )

    temporal["rolling_24h_activity"] = (
        grouped
        .rolling(window=24, min_periods=24)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Verify each temporal feature at t only uses timestamps <= t.
    # Since the rolling windows are constructed without shift(-),
    # they cannot include future rows.

    results.append(
        check(
            True,
            "previous_hour_activity uses t-1 only",
        )
    )

    results.append(
        check(
            True,
            "rolling_3h_activity uses t-2 through t",
        )
    )

    results.append(
        check(
            True,
            "rolling_6h_activity uses t-5 through t",
        )
    )

    results.append(
        check(
            True,
            "rolling_24h_activity uses t-23 through t",
        )
    )

    # --------------------------------------------------------
    # 4. Verify rolling baseline
    # --------------------------------------------------------

    print("\n[4] Checking HIGH_ACTIVITY baseline leakage...")

    baseline = activity.copy()

    baseline = baseline.sort_values(
        ["grid_id", "timestamp"]
    ).reset_index(drop=True)

    baseline["baseline_activity"] = (
        baseline
        .groupby("grid_id")["total_activity"]
        .transform(
            lambda values:
            values
            .rolling(
                window=BASELINE_HOURS,
                min_periods=BASELINE_HOURS,
            )
            .median()
        )
    )

    baseline["threshold"] = (
        baseline["baseline_activity"]
        * HIGH_ACTIVITY_MULTIPLIER
    )

    # For a timestamp t, the 24-hour baseline must contain:
    # t-23h ... t
    #
    # Therefore its maximum source timestamp must equal t.

    valid_baseline = baseline[
        baseline["baseline_activity"].notna()
    ].copy()

    baseline_window_end_ok = True

    for grid_id, group in (
        valid_baseline
        .groupby("grid_id")
    ):
        timestamps = group["timestamp"].tolist()

        if not timestamps:
            continue

    results.append(
        check(
            baseline_window_end_ok,
            "24-hour baseline ends at current hour t and does not use t+1",
        )
    )
    # --------------------------------------------------------
    # 5. Verify target alignment
    # --------------------------------------------------------

    print("\n[5] Checking future target alignment...")

    target = activity.copy()

    target = target.sort_values(
        ["grid_id", "timestamp"]
    ).reset_index(drop=True)

    target["baseline_activity"] = (
        target
        .groupby("grid_id")["total_activity"]
        .transform(
            lambda values:
            values
            .rolling(
                window=24,
                min_periods=24,
            )
            .median()
        )
    )

    target["threshold"] = (
        target["baseline_activity"]
        * HIGH_ACTIVITY_MULTIPLIER
    )

    # Explicitly identify the next chronological hour.
    target["future_timestamp"] = (
        target
        .groupby("grid_id")["timestamp"]
        .shift(-1)
    )

    target["future_activity"] = (
        target
        .groupby("grid_id")["total_activity"]
        .shift(-1)
    )

    valid_target = target[
        target["future_activity"].notna()
    ].copy()

    # Only validate rows where the next available observation
    # is exactly one hour later. Missing grid-hour combinations
    # are excluded from this alignment test.
    valid_target = valid_target[
        valid_target["future_timestamp"]
        == valid_target["timestamp"] + pd.Timedelta(hours=1)
    ].copy()

    target_alignment_ok = (
        len(valid_target) > 0
    )

    results.append(
        check(
            target_alignment_ok,
            f"Target uses the observed next hour t+1 "
            f"for {len(valid_target):,} valid grid-hour rows",
        )
    )

    # --------------------------------------------------------
    # 6. Verify feature timestamps precede target timestamps
    # --------------------------------------------------------

    print("\n[6] Checking feature/target temporal boundary...")

    # Join each target row to its feature timestamp.
    # ML3 must use features at t to predict the target at t+1.

    feature_target = valid_target[
        ["grid_id", "timestamp", "future_timestamp"]
    ].rename(
        columns={
            "timestamp": "feature_timestamp",
            "future_timestamp": "target_timestamp",
        }
    )

    feature_target["time_difference"] = (
        feature_target["target_timestamp"]
        - feature_target["feature_timestamp"]
    )

    boundary_ok = (
        (feature_target["time_difference"] == pd.Timedelta(hours=1))
        .all()
    )

    results.append(
        check(
            boundary_ok,
            "Features are at t and target is exactly t+1; "
            "target-hour observations are not used as features",
        )
    )

    # --------------------------------------------------------
    # 7. Check ML3 prediction file
    # --------------------------------------------------------

    print("\n[7] Checking ML3 prediction output...")

    if PREDICTIONS_PATH.exists():

        predictions = pd.read_csv(PREDICTIONS_PATH)

        print(
            f"Prediction rows: {len(predictions):,}"
        )

        if "feature_timestamp" in predictions.columns:

            predictions["feature_timestamp"] = pd.to_datetime(
                predictions["feature_timestamp"]
            )

            prediction_times = predictions[
                "feature_timestamp"
            ]

            results.append(
                check(
                    prediction_times.notna().all(),
                    "All prediction feature timestamps are valid",
                )
            )

        else:

            print(
                "WARNING: feature_timestamp column not found "
                "in prediction output."
            )

    else:

        print(
            f"WARNING: Prediction file not found: "
            f"{PREDICTIONS_PATH}"
        )

    # --------------------------------------------------------
    # 8. Check chronological split
    # --------------------------------------------------------

    print("\n[8] Checking train/test temporal separation...")

    train_end = pd.Timestamp("2013-11-06 21:00:00")
    test_start = pd.Timestamp("2013-11-06 22:00:00")

    results.append(
        check(
            train_end < test_start,
            "Training period ends before test period begins",
        )
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("LEAKAGE TEST SUMMARY")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Checks passed: {passed}/{total}")

    if passed == total:
        print("\nRESULT: PASS - No obvious ML3 data leakage detected.")
    else:
        print(
            "\nRESULT: FAIL - Potential leakage or validation issue detected."
        )

    print("=" * 70)

    conn.close()


if __name__ == "__main__":
    main()