from pathlib import Path
import sqlite3
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(
    0,
    str(PROJECT_ROOT / "phase1")
)

import numpy as np
import pandas as pd

from np3_alert import add_baselines
# ============================================================
# ML4 CONFIGURATION
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)
NP3_ALERT_FILE = (
    PROJECT_ROOT
    / "phase1"
    / "output"
    / "network_alerts.csv"
)
ML3_PREDICTIONS_FILE = (
    PROJECT_ROOT
    / "phase6"
    / "ml3_predictions.csv"
)
REPORT_FILE = (
    PROJECT_ROOT
    / "phase6"
    / "ML4_Anomaly_Report.md"
)
EVALUATION_FILE = (
    PROJECT_ROOT
    / "phase6"
    / "ml4_evaluation.json"
)
ANOMALY_THRESHOLD = 0.50
# ============================================================
# LOAD HOURLY ACTIVITY
# ============================================================
def load_hourly_activity():
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            grid_id,
            event_time AS timestamp,
            sms_count,
            call_count,
            internet_volume
        FROM fact_network_activity
        ORDER BY grid_id, event_time
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty:
        raise ValueError("No activity data found.")
    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )
    df["total_activity"] = (
        df["sms_count"].fillna(0)
        + df["call_count"].fillna(0)
        + df["internet_volume"].fillna(0)
    )
    return df[
        [
            "grid_id",
            "timestamp",
            "total_activity",
        ]
    ]
# ============================================================
# LOAD NP3 ALERTS
# ============================================================
def load_np3_alerts():
    if not NP3_ALERT_FILE.exists():
        raise FileNotFoundError(
            f"NP3 alert file not found: {NP3_ALERT_FILE}"
        )
    alerts = pd.read_csv(
        NP3_ALERT_FILE
    )
    alerts["grid_id"] = pd.to_numeric(
        alerts["grid_id"],
        errors="raise",
    ).astype(int)
    alerts["timestamp"] = pd.to_datetime(
        alerts["timestamp"]
    )
    return alerts
# ============================================================
# LOAD ML3 PREDICTIONS
# ============================================================
def load_ml3_predictions():
    if not ML3_PREDICTIONS_FILE.exists():
        raise FileNotFoundError(
            f"ML3 prediction file not found: "
            f"{ML3_PREDICTIONS_FILE}"
        )
    predictions = pd.read_csv(
        ML3_PREDICTIONS_FILE
    )
    predictions["grid_id"] = pd.to_numeric(
        predictions["grid_id"],
        errors="raise",
    ).astype(int)
    predictions["feature_timestamp"] = pd.to_datetime(
        predictions["feature_timestamp"]
    )
    predictions["prediction_timestamp"] = pd.to_datetime(
        predictions["prediction_timestamp"]
    )
    return predictions
# ============================================================
# CALCULATE ANOMALY SCORE
# ============================================================
def calculate_anomaly_scores(df):
    df = df.copy()
    df["hour_of_day"] = (
        df["timestamp"].dt.hour
    )
    print(
        "Calculating hour-of-day historical baselines..."
    )
    # Reuse NP3's generalized baseline implementation.
    #
    # Each grid/hour-of-day bucket contains observations
    # from multiple days rather than only one day.
    df = add_baselines(
        df,
        ["grid_id", "hour_of_day"],
        leave_one_out=True,
    )
    df["anomaly_score"] = np.where(
        df["baseline_activity"] > 0,
        (
            df["total_activity"]
            - df["baseline_activity"]
        )
        / df["baseline_activity"],
        np.nan,
    )
    df["anomaly_direction"] = np.select(
        [
            df["anomaly_score"] >= ANOMALY_THRESHOLD,
            df["anomaly_score"] <= -ANOMALY_THRESHOLD,
        ],
        [
            "HIGH",
            "LOW",
        ],
        default="NORMAL",
    )
    df["anomaly_flag"] = (
        df["anomaly_direction"]
        != "NORMAL"
    ).astype(int)
    def build_reason(row):
        if pd.isna(row["baseline_activity"]):
            return "No historical baseline available."
        if row["anomaly_direction"] == "HIGH":
            return (
                f"Activity {row['total_activity']:.2f} is "
                f"{row['anomaly_score'] * 100:.1f}% above the "
                f"hour-of-day baseline "
                f"({row['baseline_activity']:.2f})."
            )
        if row["anomaly_direction"] == "LOW":
            return (
                f"Activity {row['total_activity']:.2f} is "
                f"{abs(row['anomaly_score']) * 100:.1f}% below the "
                f"hour-of-day baseline "
                f"({row['baseline_activity']:.2f})."
            )
        return (
            f"Activity {row['total_activity']:.2f} is within "
            f"the ±{ANOMALY_THRESHOLD * 100:.0f}% normal range "
            f"around the baseline "
            f"({row['baseline_activity']:.2f})."
        )
    df["reason"] = df.apply(
        build_reason,
        axis=1,
    )
    return df
# ============================================================
# VERIFY HISTORICAL BUCKET DEPTH
# ============================================================
def calculate_bucket_statistics(df):
    bucket_counts = (
        df.groupby(
            [
                "grid_id",
                "hour_of_day",
            ]
        )
        .size()
        .reset_index(
            name="history_count"
        )
    )
    return bucket_counts
# ============================================================
# THREE-WAY COMPARISON
# ============================================================
def create_three_way_comparison(
    anomaly_scores,
    ml3_predictions,
    np3_alerts,
):
    anomaly_scores = anomaly_scores.copy()
    ml3_predictions = ml3_predictions.copy()
    np3_alerts = np3_alerts.copy()

    anomaly_scores["grid_id"] = pd.to_numeric(
        anomaly_scores["grid_id"],
        errors="raise",
    ).astype(int)

    ml3_predictions["grid_id"] = pd.to_numeric(
        ml3_predictions["grid_id"],
        errors="raise",
    ).astype(int)

    np3_alerts["grid_id"] = pd.to_numeric(
        np3_alerts["grid_id"],
        errors="raise",
    ).astype(int)
    # ML3 test period is the common comparison population.
    comparison = ml3_predictions[
        [
            "grid_id",
            "prediction_timestamp",
            "MODEL_PREDICTION",
            "prediction_probability",
        ]
    ].copy()
    comparison = comparison.merge(
        anomaly_scores[
            [
                "grid_id",
                "timestamp",
                "anomaly_score",
                "anomaly_direction",
                "anomaly_flag",
                "total_activity",
                "baseline_activity",
            ]
        ],
        left_on=[
            "grid_id",
            "prediction_timestamp",
        ],
        right_on=[
            "grid_id",
            "timestamp",
        ],
        how="left",
    )
    np3_keys = (
        np3_alerts[
            [
                "grid_id",
                "timestamp",
            ]
        ]
        .drop_duplicates()
    )
    np3_keys["NP3_ALERT"] = 1
    comparison = comparison.merge(
        np3_keys,
        left_on=[
            "grid_id",
            "prediction_timestamp",
        ],
        right_on=[
            "grid_id",
            "timestamp",
        ],
        how="left",
    )
    comparison["NP3_ALERT"] = (
        comparison["NP3_ALERT"]
        .fillna(0)
        .astype(int)
    )
    comparison["ML4_ANOMALY"] = (
        comparison["anomaly_flag"]
        .fillna(0)
        .astype(int)
    )
    comparison["ML3_PREDICTION"] = (
        comparison["MODEL_PREDICTION"]
        .astype(int)
    )
    comparison["comparison_category"] = np.select(
        [
            (
                (comparison["ML4_ANOMALY"] == 1)
                & (comparison["NP3_ALERT"] == 1)
                & (comparison["ML3_PREDICTION"] == 1)
            ),
            (
                (comparison["ML4_ANOMALY"] == 1)
                & (comparison["NP3_ALERT"] == 1)
            ),
            (
                (comparison["ML4_ANOMALY"] == 1)
                & (comparison["ML3_PREDICTION"] == 1)
            ),
            (
                (comparison["NP3_ALERT"] == 1)
                & (comparison["ML3_PREDICTION"] == 1)
            ),
            (
                (comparison["ML4_ANOMALY"] == 1)
            ),
            (
                (comparison["NP3_ALERT"] == 1)
            ),
            (
                (comparison["ML3_PREDICTION"] == 1)
            ),
        ],
        [
            "ALL_THREE",
            "ML4_NP3",
            "ML4_ML3",
            "NP3_ML3",
            "ML4_ONLY",
            "NP3_ONLY",
            "ML3_ONLY",
        ],
        default="NONE",
    )
    return comparison
# ============================================================
# SAVE DATABASE TABLES
# ============================================================
def save_tables(
    anomaly_scores,
    comparison,
):
    conn = sqlite3.connect(DB_PATH)
    anomaly_output = anomaly_scores[
        [
            "grid_id",
            "timestamp",
            "total_activity",
            "hour_of_day",
            "baseline_activity",
            "anomaly_score",
            "anomaly_direction",
            "anomaly_flag",
            "reason",
        ]
    ].copy()
    anomaly_output.to_sql(
        "network_anomaly_scores",
        conn,
        if_exists="replace",
        index=False,
    )
    comparison.to_sql(
        "network_anomaly_comparison",
        conn,
        if_exists="replace",
        index=False,
    )
    conn.close()
# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("ML4 - Anomaly Baseline")
    print("=" * 70)
    print("\n[1] Loading hourly activity...")
    activity = load_hourly_activity()
    print(
        f"Activity rows: {len(activity):,}"
    )
    print(
        "Activity timestamps:",
        activity["timestamp"].min(),
        "->",
        activity["timestamp"].max(),
    )
    print("\n[2] Calculating anomaly scores...")
    anomaly_scores = calculate_anomaly_scores(
        activity
    )
    print(
        f"Anomaly score rows: "
        f"{len(anomaly_scores):,}"
    )
    print("\n[3] Verifying history depth...")
    bucket_counts = calculate_bucket_statistics(
        anomaly_scores
    )
    print(
        f"Grid/hour-of-day buckets: "
        f"{len(bucket_counts):,}"
    )
    print(
        "Minimum history count:",
        int(bucket_counts["history_count"].min()),
    )
    print(
        "Maximum history count:",
        int(bucket_counts["history_count"].max()),
    )
    print(
        "Average history count:",
        round(
            bucket_counts["history_count"].mean(),
            2,
        ),
    )
    if bucket_counts["history_count"].min() <= 1:
        raise AssertionError(
            "Hour-of-day baseline does not use "
            "more than one day of history."
        )
    print("\n[4] Anomaly summary...")
    direction_counts = (
        anomaly_scores[
            "anomaly_direction"
        ]
        .value_counts()
        .to_dict()
    )
    print(
        "HIGH :",
        direction_counts.get("HIGH", 0),
    )
    print(
        "LOW  :",
        direction_counts.get("LOW", 0),
    )
    print(
        "NORMAL:",
        direction_counts.get("NORMAL", 0),
    )
    if direction_counts.get("HIGH", 0) == 0:
        raise AssertionError(
            "No HIGH anomalies were produced."
        )
    if direction_counts.get("LOW", 0) == 0:
        raise AssertionError(
            "No LOW anomalies were produced."
        )
    print("\n[5] Loading ML3 predictions and NP3 alerts...")
    ml3_predictions = load_ml3_predictions()
    np3_alerts = load_np3_alerts()
    print(
        f"ML3 prediction rows: "
        f"{len(ml3_predictions):,}"
    )
    print(
        f"NP3 alert rows: "
        f"{len(np3_alerts):,}"
    )
    print("\n[6] Creating three-way comparison...")
    comparison = create_three_way_comparison(
        anomaly_scores,
        ml3_predictions,
        np3_alerts,
    )
    print(
        f"Comparison rows: "
        f"{len(comparison):,}"
    )
    category_counts = (
        comparison[
            "comparison_category"
        ]
        .value_counts()
        .to_dict()
    )
    print("\nTHREE-WAY COMPARISON")
    categories = [
        "ALL_THREE",
        "ML4_NP3",
        "ML4_ML3",
        "NP3_ML3",
        "ML4_ONLY",
        "NP3_ONLY",
        "ML3_ONLY",
        "NONE",
    ]
    for category in categories:
        print(
            f"{category:12s}: "
            f"{category_counts.get(category, 0):,}"
        )
    print("\n[7] Saving database tables...")
    save_tables(
        anomaly_scores,
        comparison,
    )
    print(
        "Saved tables:"
    )
    print(
        "  network_anomaly_scores"
    )
    print(
        "  network_anomaly_comparison"
    )
    print("\n[8] Finding representative disagreement...")
    disagreement_order = [
        "ML4_ONLY",
        "ML4_NP3",
        "ML4_ML3",
        "NP3_ONLY",
        "ML3_ONLY",
        "NP3_ML3",
    ]
    disagreement = None
    for category in disagreement_order:
        rows = comparison[
            comparison["comparison_category"]
            == category
        ]
        if not rows.empty:
            disagreement = rows.iloc[0]
            break
    if disagreement is not None:
        disagreement_text = f"""
### Representative disagreement

**Category:** {disagreement["comparison_category"]}

- Grid: {disagreement["grid_id"]}
- Timestamp: {disagreement["prediction_timestamp"]}
- Activity: {disagreement["total_activity"]:.2f}
- Hour-of-day baseline: {disagreement["baseline_activity"]:.2f}
- ML4 anomaly score: {disagreement["anomaly_score"]:.4f}
- ML4 direction: {disagreement["anomaly_direction"]}
- ML4 anomaly flag: {int(disagreement["ML4_ANOMALY"])}
- NP3 alert: {int(disagreement["NP3_ALERT"])}
- ML3 prediction: {int(disagreement["ML3_PREDICTION"])}

The disagreement occurs because ML4 evaluates deviation from the
multi-day hour-of-day historical baseline, while NP3 applies
within-day rule thresholds and ML3 predicts the next hour's
P90-based HIGH_ACTIVITY condition. These methods therefore measure
different aspects of unusual network behavior.
"""
    else:
        disagreement_text = """
### Representative disagreement

No disagreement was found in the common ML3 test population.
"""

    print("\n[9] Writing evaluation report...")
    report = f"""# ML4 — Anomaly Baseline Evaluation

## 1. Objective

ML4 adds a simple, explainable anomaly scorer based on historical
network activity. It does not use advanced unsupervised machine
learning.

## 2. Baseline

The anomaly baseline is calculated per:

- grid
- hour of day

The baseline is the leave-one-out median of the observations in
the same grid/hour-of-day bucket.

This differs from NP3's within-day baseline because each hour-of-day
bucket contains observations from multiple dates.

## 3. History Verification

- Grid/hour-of-day buckets: {len(bucket_counts):,}
- Minimum observations per bucket: {int(bucket_counts["history_count"].min())}
- Maximum observations per bucket: {int(bucket_counts["history_count"].max())}
- Average observations per bucket: {bucket_counts["history_count"].mean():.2f}

The minimum bucket depth is greater than one, confirming that the
ML4 baseline uses more than one day's observations.

## 4. Anomaly Score

The percentage deviation is:

`(current_activity - baseline_activity) / baseline_activity`

Threshold:

`±{ANOMALY_THRESHOLD:.2f}`

Therefore:

- HIGH = at least 50% above baseline
- LOW = at least 50% below baseline
- NORMAL = within ±50% of baseline

## 5. Anomaly Results

- HIGH anomalies: {direction_counts.get("HIGH", 0):,}
- LOW anomalies: {direction_counts.get("LOW", 0):,}
- NORMAL observations: {direction_counts.get("NORMAL", 0):,}

Both high and low anomaly directions are present.

## 6. Three-Way Comparison

Comparison is restricted to the ML3 test population so all three
methods operate on the same grid-hour observations.

| Category | Count |
|---|---:|
| ALL_THREE | {category_counts.get("ALL_THREE", 0):,} |
| ML4_NP3 | {category_counts.get("ML4_NP3", 0):,} |
| ML4_ML3 | {category_counts.get("ML4_ML3", 0):,} |
| NP3_ML3 | {category_counts.get("NP3_ML3", 0):,} |
| ML4_ONLY | {category_counts.get("ML4_ONLY", 0):,} |
| NP3_ONLY | {category_counts.get("NP3_ONLY", 0):,} |
| ML3_ONLY | {category_counts.get("ML3_ONLY", 0):,} |
| NONE | {category_counts.get("NONE", 0):,} |
{disagreement_text}

## 7. Interpretation

ML4 is intentionally explainable. Its score directly states how
far the current activity is from the grid's historical behavior for
the same hour of day.

NP3 is rule-based and uses within-day comparisons plus an activity
floor. ML3 is a supervised classifier predicting the next hour's
P90-based HIGH_ACTIVITY condition.

Consequently, disagreement between the methods is expected and
useful: it identifies observations where historical seasonal
behavior, deterministic rules, and supervised prediction do not
produce the same assessment.

## 8. Limitations

The anomaly threshold of ±50% is a simple operational threshold,
not a learned statistical confidence interval.

The ML4 baseline is based on the available seven-day warehouse
history, so it should be interpreted as a historical behavioral
reference rather than a long-term seasonal model.
"""
    REPORT_FILE.write_text(
        report,
        encoding="utf-8",
    )
    evaluation = {
        "rows": int(len(anomaly_scores)),
        "history_bucket_count": int(len(bucket_counts)),
        "min_history_count": int(
            bucket_counts["history_count"].min()
        ),
        "max_history_count": int(
            bucket_counts["history_count"].max()
        ),
        "high_anomalies": int(
            direction_counts.get("HIGH", 0)
        ),
        "low_anomalies": int(
            direction_counts.get("LOW", 0)
        ),
        "normal_observations": int(
            direction_counts.get("NORMAL", 0)
        ),
        "comparison_rows": int(
            len(comparison)
        ),
        "comparison_categories": {
            key: int(value)
            for key, value in category_counts.items()
        },
    }
    EVALUATION_FILE.write_text(
        json.dumps(
            evaluation,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Report saved: {REPORT_FILE}"
    )
    print(
        f"Evaluation saved: {EVALUATION_FILE}"
    )
    print("\n" + "=" * 70)
    print("ML4 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()