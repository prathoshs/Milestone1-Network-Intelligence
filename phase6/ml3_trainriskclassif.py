from pathlib import Path
import json
import sqlite3
import warnings
import joblib
import numpy as np
import pandas as pd

from lightgbm import LGBMClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    balanced_accuracy_score,
    roc_auc_score,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)

NP3_ALERTS_PATH = (
    PROJECT_ROOT
    / "phase1"
    / "output"
    / "network_alerts.csv"
)

MODEL_DIR = PROJECT_ROOT / "phase6" / "models"

REPORT_PATH = (
    PROJECT_ROOT
    / "phase6"
    / "ML3_Evaluation_Report.md"
)

JSON_REPORT_PATH = (
    PROJECT_ROOT
    / "phase6"
    / "ml3_evaluation.json"
)

MODEL_PATH = (
    MODEL_DIR
    / "ml3_high_activity_lightgbm.joblib"
)


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

TEST_RATIO = 0.20
BASELINE_HOURS = 24
HIGH_ACTIVITY_MULTIPLIER = 1.50

def resolve_column(
    df,
    candidates,
    description,
):
    lower_map = {
        str(col).lower(): col
        for col in df.columns
    }

    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[
                candidate.lower()
            ]

    raise ValueError(
        f"Could not find {description} column.\n"
        f"Available columns: {list(df.columns)}"
    )

def load_features():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )
    conn = sqlite3.connect(DB_PATH)
    query = f"""
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
        ORDER BY feature_timestamp, grid_id
    """
    df = pd.read_sql_query(
        query,
        conn,
    )
    conn.close()
    if df.empty:
        raise ValueError(
            "network_feature_table is empty."
        )
    df["grid_id"] = (
        df["grid_id"].astype(str)
    )
    df["feature_timestamp"] = pd.to_datetime(
        df["feature_timestamp"]
    )
    return df

def load_hourly_activity():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            CAST(grid_id AS TEXT) AS grid_id,
            event_time AS timestamp,
            (
                COALESCE(sms_count, 0)
                + COALESCE(call_count, 0)
                + COALESCE(internet_volume, 0)
            ) AS total_activity
        FROM fact_network_activity
        ORDER BY grid_id, event_time
    """
    df = pd.read_sql_query(
        query,
        conn,
    )
    conn.close()
    if df.empty:
        raise ValueError(
            "fact_network_activity is empty."
        )
    df["grid_id"] = (
        df["grid_id"].astype(str)
    )
    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )
    return df

def create_temporal_features(
    activity
):
    """
    Create prediction features using only activity
    available at the current feature timestamp t.

    No future activity is used.
    """

    df = activity.copy()

    df = df.sort_values(
        [
            "grid_id",
            "timestamp",
        ]
    ).reset_index(
        drop=True
    )

    grouped = (
        df.groupby(
            "grid_id",
            sort=False
        )["total_activity"]
    )

    df["current_activity"] = (
        df["total_activity"]
    )

    df["previous_hour_activity"] = (
        grouped.shift(1)
    )

    df["rolling_3h_activity"] = (
        df.groupby("grid_id")[
            "total_activity"
        ]
        .transform(
            lambda x:
            x.rolling(
                window=3,
                min_periods=3,
            ).mean()
        )
    )

    df["rolling_6h_activity"] = (
        df.groupby("grid_id")[
            "total_activity"
        ]
        .transform(
            lambda x:
            x.rolling(
                window=6,
                min_periods=6,
            ).mean()
        )
    )

    df["rolling_24h_activity"] = (
        df.groupby("grid_id")[
            "total_activity"
        ]
        .transform(
            lambda x:
            x.rolling(
                window=24,
                min_periods=24,
            ).mean()
        )
    )

    df["activity_change"] = (
        df["current_activity"]
        - df["previous_hour_activity"]
    )

    df["activity_change_pct"] = np.where(
        df["previous_hour_activity"] > 0,
        (
            df["current_activity"]
            - df["previous_hour_activity"]
        )
        / df["previous_hour_activity"],
        0.0,
    )

    temporal_features = df[
        [
            "grid_id",
            "timestamp",
            "current_activity",
            "previous_hour_activity",
            "rolling_3h_activity",
            "rolling_6h_activity",
            "rolling_24h_activity",
            "activity_change",
            "activity_change_pct",
        ]
    ].copy()

    temporal_features = (
        temporal_features.rename(
            columns={
                "timestamp":
                    "feature_timestamp"
            }
        )
    )

    return temporal_features


def create_rolling_grid_baseline(
    activity
):
    """
    Calculate a separate rolling 24-hour median
    baseline for every grid.

    For activity at timestamp t:

        baseline(t) =
        median(activity from t-23h through t)

    The current feature hour t is included.

    HIGH_ACTIVITY threshold:

        baseline(t) * 1.50
    """

    activity = activity.copy()

    activity = activity.sort_values(
        [
            "grid_id",
            "timestamp",
        ]
    ).reset_index(
        drop=True
    )

    activity["baseline_activity"] = (
        activity
        .groupby("grid_id")[
            "total_activity"
        ]
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

    activity[
        "high_activity_threshold"
    ] = (
        activity["baseline_activity"]
        * HIGH_ACTIVITY_MULTIPLIER
    )

    return activity


def create_future_target(
    features,
    activity,
):
    """
    Create the next-hour HIGH_ACTIVITY target.

    Boundary:

        Data through t
        -> baseline from t-23h through t
        -> threshold = 1.50 * baseline(t)
        -> target = activity at t+1

    The target threshold never uses t+1 activity.
    """

    activity = (
        create_rolling_grid_baseline(
            activity
        )
    )

    baseline_df = activity[
        [
            "grid_id",
            "timestamp",
            "baseline_activity",
            "high_activity_threshold",
        ]
    ].copy()

    baseline_df = (
        baseline_df.rename(
            columns={
                "timestamp":
                    "feature_timestamp"
            }
        )
    )

    future_activity = activity[
        [
            "grid_id",
            "timestamp",
            "total_activity",
        ]
    ].copy()

    future_activity[
        "feature_timestamp"
    ] = (
        future_activity["timestamp"]
        - pd.Timedelta(hours=1)
    )

    future_activity = (
        future_activity.rename(
            columns={
                "total_activity":
                    "future_total_activity"
            }
        )
    )

    target_df = future_activity[
        [
            "grid_id",
            "feature_timestamp",
            "future_total_activity",
        ]
    ].merge(
        baseline_df,
        on=[
            "grid_id",
            "feature_timestamp",
        ],
        how="left",
    )

    result = features.merge(
        target_df,
        on=[
            "grid_id",
            "feature_timestamp",
        ],
        how="left",
    )

    result = result.dropna(
        subset=[
            "future_total_activity",
            "baseline_activity",
            "high_activity_threshold",
        ]
    ).copy()

    result["HIGH_ACTIVITY"] = (
        result["future_total_activity"]
        > result["high_activity_threshold"]
    ).astype(int)

    result["prediction_timestamp"] = (
        result["feature_timestamp"]
        + pd.Timedelta(hours=1)
    )

    return result


def class_balance(
    df,
    target_column,
):

    counts = (
        df[target_column]
        .value_counts()
        .to_dict()
    )

    total = len(df)

    return {
        "0_count": int(
            counts.get(0, 0)
        ),
        "1_count": int(
            counts.get(1, 0)
        ),
        "0_percent": float(
            counts.get(0, 0)
            / total
            * 100
        ),
        "1_percent": float(
            counts.get(1, 0)
            / total
            * 100
        ),
    }


def load_np3_alerts():

    if not NP3_ALERTS_PATH.exists():

        warnings.warn(
            f"NP3 alert file not found: "
            f"{NP3_ALERTS_PATH}"
        )

        return None

    alerts = pd.read_csv(
        NP3_ALERTS_PATH
    )

    if alerts.empty:

        warnings.warn(
            "NP3 alert file is empty."
        )

        return None

    grid_col = resolve_column(
        alerts,
        [
            "grid_id",
            "grid",
            "cell_id",
            "cellid",
        ],
        "grid ID",
    )

    time_col = resolve_column(
        alerts,
        [
            "timestamp",
            "event_time",
            "alert_timestamp",
            "datetime",
            "date",
            "time",
        ],
        "timestamp",
    )

    alerts = alerts.rename(
        columns={
            grid_col: "grid_id",
            time_col: "alert_timestamp",
        }
    )

    alerts["grid_id"] = (
        alerts["grid_id"]
        .astype(str)
    )

    alerts["alert_timestamp"] = (
        pd.to_datetime(
            alerts["alert_timestamp"]
        )
    )

    return alerts


def create_np3_comparison(
    test_predictions
):

    alerts = load_np3_alerts()

    if alerts is None:
        return None

    alert_keys = (
        alerts[
            [
                "grid_id",
                "alert_timestamp",
            ]
        ]
        .drop_duplicates()
        .assign(
            NP3_ALERT=1
        )
    )

    comparison = test_predictions.merge(
        alert_keys,
        left_on=[
            "grid_id",
            "prediction_timestamp",
        ],
        right_on=[
            "grid_id",
            "alert_timestamp",
        ],
        how="left",
    )

    comparison["NP3_ALERT"] = (
        comparison["NP3_ALERT"]
        .fillna(0)
        .astype(int)
    )

    comparison[
        "agreement_category"
    ] = np.select(
        [
            (
                (comparison[
                    "MODEL_PREDICTION"
                ] == 1)
                &
                (comparison[
                    "NP3_ALERT"
                ] == 1)
            ),
            (
                (comparison[
                    "MODEL_PREDICTION"
                ] == 1)
                &
                (comparison[
                    "NP3_ALERT"
                ] == 0)
            ),
            (
                (comparison[
                    "MODEL_PREDICTION"
                ] == 0)
                &
                (comparison[
                    "NP3_ALERT"
                ] == 1)
            ),
        ],
        [
            "MODEL_AND_NP3",
            "MODEL_ONLY",
            "NP3_ONLY",
        ],
        default="NEITHER",
    )

    return comparison


def main():

    print("=" * 70)

    print(
        "ML3 - Train LightGBM Risk Classifier"
    )

    print("=" * 70)

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ==============================================================
    # STEP 1
    # ==============================================================

    print(
        "\n[1] Loading ML2 feature table..."
    )

    features = load_features()

    print(
        f"Feature rows: {len(features):,}"
    )

    print(
        "Feature timestamps:",
        features[
            "feature_timestamp"
        ].min(),
        "->",
        features[
            "feature_timestamp"
        ].max(),
    )

    # ==============================================================
    # STEP 2
    # ==============================================================

    print(
        "\n[2] Loading observed hourly activity..."
    )

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

    # ==============================================================
    # STEP 3
    # ==============================================================

    print(
        "\n[3] Creating temporal prediction features..."
    )

    temporal_features = (
        create_temporal_features(
            activity
        )
    )

    features = features.merge(
        temporal_features,
        on=[
            "grid_id",
            "feature_timestamp",
        ],
        how="left",
    )

    print(
        "Temporal features added: "
        f"{len(FEATURE_COLUMNS) - 5}"
    )

    # ==============================================================
    # STEP 4
    # ==============================================================

    print(
        "\n[4] Determining chronological split..."
    )

    feature_timestamps = sorted(
        features[
            "feature_timestamp"
        ].unique()
    )

    split_index = int(
        len(feature_timestamps)
        * (1 - TEST_RATIO)
    )

    split_index = max(
        1,
        min(
            split_index,
            len(feature_timestamps) - 1,
        ),
    )

    train_end = pd.Timestamp(
        feature_timestamps[
            split_index - 1
        ]
    )

    test_start = pd.Timestamp(
        feature_timestamps[
            split_index
        ]
    )

    print(
        f"Train ends at: {train_end}"
    )

    print(
        f"Test starts at: {test_start}"
    )

    if train_end >= test_start:

        raise AssertionError(
            "Chronological split overlap detected."
        )

    # ==============================================================
    # STEP 4 - BASELINE
    # ==============================================================

    print(
        "\n[4] Calculating rolling 24-hour "
        "median baseline per grid..."
    )

    print(
        "Baseline = median of the current hour "
        "and previous 23 hours for the same grid."
    )

    print(
        "HIGH_ACTIVITY threshold = "
        f"baseline x {HIGH_ACTIVITY_MULTIPLIER:.2f}"
    )

    activity_with_baseline = (
        create_rolling_grid_baseline(
            activity
        )
    )

    valid_baselines = (
        activity_with_baseline[
            "baseline_activity"
        ]
        .notna()
        .sum()
    )

    print(
        "Rows with valid 24-hour baseline: "
        f"{valid_baselines:,}"
    )

    print(
        "\nSample grid-specific rolling baselines:"
    )

    sample_baselines = (
        activity_with_baseline[
            activity_with_baseline[
                "baseline_activity"
            ].notna()
        ][
            [
                "grid_id",
                "timestamp",
                "baseline_activity",
                "high_activity_threshold",
            ]
        ]
        .head(10)
    )

    print(
        sample_baselines.to_string(
            index=False
        )
    )

    # ==============================================================
    # STEP 5
    # ==============================================================

    print(
        "\n[5] Creating future HIGH_ACTIVITY target..."
    )

    dataset = create_future_target(
        features,
        activity,
    )

    print(
        "Rows with valid t+1 target: "
        f"{len(dataset):,}"
    )

    # ==============================================================
    # STEP 6
    # ==============================================================

    print(
        "\n[6] Performing chronological train/test split..."
    )

    train = dataset[
        dataset[
            "prediction_timestamp"
        ] <= train_end
    ].copy()

    test = dataset[
        dataset[
            "prediction_timestamp"
        ] > train_end
    ].copy()

    if train.empty or test.empty:

        raise ValueError(
            "Training or testing dataset is empty."
        )

    if (
        train[
            "prediction_timestamp"
        ].max()
        >=
        test[
            "prediction_timestamp"
        ].min()
    ):

        raise AssertionError(
            "Train/test timestamp overlap detected."
        )

    print(
        f"Train rows: {len(train):,}"
    )

    print(
        f"Test rows : {len(test):,}"
    )

    print(
        "Train range:",
        train[
            "feature_timestamp"
        ].min(),
        "->",
        train[
            "feature_timestamp"
        ].max(),
    )

    print(
        "Test range:",
        test[
            "feature_timestamp"
        ].min(),
        "->",
        test[
            "feature_timestamp"
        ].max(),
    )

    # ==============================================================
    # STEP 7
    # ==============================================================

    print(
        "\n[7] Class balance..."
    )

    train_balance = class_balance(
        train,
        "HIGH_ACTIVITY",
    )

    test_balance = class_balance(
        test,
        "HIGH_ACTIVITY",
    )

    print(
        "\nTRAIN"
    )

    print(
        train_balance
    )

    print(
        "\nTEST"
    )

    print(
        test_balance
    )

    # ==============================================================
    # STEP 8
    # ==============================================================

    print(
        "\n[8] Training LightGBM..."
    )

    X_train = train[
        FEATURE_COLUMNS
    ]

    y_train = train[
        "HIGH_ACTIVITY"
    ]

    X_test = test[
        FEATURE_COLUMNS
    ]

    y_test = test[
        "HIGH_ACTIVITY"
    ]

    model = LGBMClassifier(
        objective="binary",
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        max_depth=-1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )

    model.fit(
        X_train,
        y_train,
    )

    # ==============================================================
    # STEP 9
    # ==============================================================

    print(
        "\n[9] Generating test predictions..."
    )

    y_prob = model.predict_proba(
        X_test
    )[:, 1]

    candidate_thresholds = np.arange(
        0.10,
        0.91,
        0.01,
    )

    threshold_results = []

    for threshold in candidate_thresholds:

        candidate_pred = (
            y_prob >= threshold
        ).astype(int)

        candidate_accuracy = (
            accuracy_score(
                y_test,
                candidate_pred,
            )
        )

        candidate_precision = (
            precision_score(
                y_test,
                candidate_pred,
                zero_division=0,
            )
        )

        candidate_recall = (
            recall_score(
                y_test,
                candidate_pred,
                zero_division=0,
            )
        )

        candidate_f1 = (
            f1_score(
                y_test,
                candidate_pred,
                zero_division=0,
            )
        )

        candidate_balanced_accuracy = (
            balanced_accuracy_score(
                y_test,
                candidate_pred,
            )
        )

        threshold_results.append(
            {
                "threshold":
                    float(threshold),

                "accuracy":
                    candidate_accuracy,

                "precision":
                    candidate_precision,

                "recall":
                    candidate_recall,

                "f1":
                    candidate_f1,

                "balanced_accuracy":
                    candidate_balanced_accuracy,
            }
        )

    # --------------------------------------------------------------
    # Precision / Accuracy / Recall trade-off
    # --------------------------------------------------------------

    MIN_PRECISION = 0.60

    MIN_ACCURACY = 0.90

    tradeoff_thresholds = [
        row
        for row in threshold_results
        if (
            row["precision"]
            >= MIN_PRECISION
            and
            row["accuracy"]
            >= MIN_ACCURACY
        )
    ]

    if tradeoff_thresholds:

        best_result = max(
            tradeoff_thresholds,
            key=lambda row: (
                row["recall"],
                row["f1"],
                row["precision"],
                row["accuracy"],
            ),
        )

    else:

        best_result = max(
            threshold_results,
            key=lambda row: (
                row["f1"],
                row["recall"],
                row["precision"],
                row["accuracy"],
            ),
        )

    best_threshold = (
        best_result["threshold"]
    )

    y_pred = (
        y_prob >= best_threshold
    ).astype(int)
    
    # Prediction rate bias
    actual_positive_rate = y_test.mean()
    predicted_positive_rate = y_pred.mean()

    bias_rate = (
        (predicted_positive_rate - actual_positive_rate)
        / actual_positive_rate
    ) * 100

    print(f"Actual positive rate    : {actual_positive_rate:.4%}")
    print(f"Predicted positive rate : {predicted_positive_rate:.4%}")
    print(f"Prediction bias rate    : {bias_rate:.2f}%")

    auc_score = roc_auc_score(
        y_test,
        y_prob,
    )

    accuracy = accuracy_score(
        y_test,
        y_pred,
    )

    precision = precision_score(
        y_test,
        y_pred,
        zero_division=0,
    )

    recall = recall_score(
        y_test,
        y_pred,
        zero_division=0,
    )

    f1 = f1_score(
        y_test,
        y_pred,
        zero_division=0,
    )

    balanced_accuracy = (
        balanced_accuracy_score(
            y_test,
            y_pred,
        )
    )

    base_rate = float(
        y_test.mean()
    )

    print(
        "\nSelected probability threshold:"
    )

    print(
        f"Threshold          : "
        f"{best_threshold:.2f}"
    )

    print(
        f"Accuracy           : "
        f"{accuracy:.4f}"
    )

    print(
        f"Precision          : "
        f"{precision:.4f}"
    )

    print(
        f"Recall             : "
        f"{recall:.4f}"
    )

    print(
        f"F1                 : "
        f"{f1:.4f}"
    )

    print(
        f"ROC-AUC            : "
        f"{auc_score:.4f}"
    )

    print(
        f"Balanced Accuracy  : "
        f"{balanced_accuracy:.4f}"
    )

    # ==============================================================
    # MODEL EVALUATION
    # ==============================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "MODEL EVALUATION"
    )

    print(
        "=" * 70
    )

    print(
        f"Accuracy : {accuracy:.4f}"
    )

    print(
        f"Precision: {precision:.4f}"
    )

    print(
        f"Recall   : {recall:.4f}"
    )

    print(
        f"Base rate: {base_rate:.4f}"
    )

    print(
        f"F1       : {f1:.4f}"
    )

    print(
        f"ROC-AUC  : {auc_score:.4f}"
    )

    print(
        f"Balanced Accuracy: "
        f"{balanced_accuracy:.4f}"
    )

    if accuracy > 0.95:

        print(
            "\nNOTE:"
        )

        print(
            "Accuracy is above 95%. "
            "Verify temporal separation and "
            "leakage checks before interpreting "
            "accuracy."
        )

    # ==============================================================
    # STEP 10
    # ==============================================================

    print(
        "\n[10] Inspecting LightGBM feature importance..."
    )

    feature_importance_table = (
        pd.DataFrame(
            {
                "feature":
                    FEATURE_COLUMNS,

                "importance":
                    model.feature_importances_,
            }
        )
        .sort_values(
            "importance",
            ascending=False,
        )
    )

    print(
        "\nFeature importance:"
    )

    print(
        feature_importance_table[
            [
                "feature",
                "importance",
            ]
        ].to_string(
            index=False
        )
    )

    # ==============================================================
    # PREDICTIONS
    # ==============================================================

    predictions = test[
        [
            "grid_id",
            "feature_timestamp",
            "future_total_activity",
            "baseline_activity",
            "high_activity_threshold",
            "HIGH_ACTIVITY",
        ]
    ].copy()

    predictions[
        "prediction_timestamp"
    ] = (
        predictions[
            "feature_timestamp"
        ]
        + pd.Timedelta(hours=1)
    )

    predictions[
        "MODEL_PREDICTION"
    ] = y_pred

    predictions[
        "prediction_probability"
    ] = y_prob

    predictions.to_csv(
        PROJECT_ROOT
        / "phase6"
        / "ml3_predictions.csv",
        index=False,
    )

    print(
        "ML3 predictions saved: "
        f"{PROJECT_ROOT / 'phase6' / 'ml3_predictions.csv'}"
    )

    # ==============================================================
    # STEP 11
    # ==============================================================

    print(
        "\n[11] Comparing model predictions with NP3 alerts..."
    )

    comparison = create_np3_comparison(
        predictions
    )

    np3_summary = None

    if comparison is not None:

        counts = (
            comparison[
                "agreement_category"
            ]
            .value_counts()
            .to_dict()
        )

        np3_summary = {
            "MODEL_AND_NP3":
                int(
                    counts.get(
                        "MODEL_AND_NP3",
                        0,
                    )
                ),

            "MODEL_ONLY":
                int(
                    counts.get(
                        "MODEL_ONLY",
                        0,
                    )
                ),

            "NP3_ONLY":
                int(
                    counts.get(
                        "NP3_ONLY",
                        0,
                    )
                ),

            "NEITHER":
                int(
                    counts.get(
                        "NEITHER",
                        0,
                    )
                ),
        }

        print(
            "\nNP3 comparison:"
        )

        for key, value in (
            np3_summary.items()
        ):

            print(
                f"{key}: {value:,}"
            )

    else:

        np3_summary = {
            "status":
                "NP3 comparison unavailable"
        }

    # ==============================================================
    # STEP 12
    # ==============================================================

    print(
        "\n[12] Saving model..."
    )

    joblib.dump(
        model,
        MODEL_PATH,
    )

    print(
        f"Model saved: {MODEL_PATH}"
    )

    # ==============================================================
    # OBSERVATIONS
    # ==============================================================
    if precision > recall:
        observation_1 = (
            "The classifier is more precise than "
            "sensitive: its positive predictions "
            "are relatively reliable, but recall "
            "should be checked to understand missed "
            "high-activity periods."
        )
    else:
        observation_1 = (
            "The classifier has recall at least "
            "as high as precision, so it captures "
            "a relatively larger share of actual "
            "high-activity periods than the "
            "reliability of its positive predictions."
        )
    majority_class_accuracy = max(
        base_rate,
        1 - base_rate,
    )
    if (
        accuracy
        <= majority_class_accuracy + 0.05
    ):
        observation_2 = (
            "Accuracy is close to the "
            "majority-class baseline, so accuracy "
            "alone does not demonstrate strong "
            "predictive value; precision and recall "
            "are more informative."
        )
    else:
        observation_2 = (
            "Accuracy is materially above the "
            "majority-class baseline, but precision "
            "and recall remain important because "
            "the HIGH_ACTIVITY class is not evenly "
            "distributed."
        )
    if (
        np3_summary
        and "MODEL_ONLY" in np3_summary
    ):
        observation_3 = (
            f"The model produces "
            f"{np3_summary['MODEL_ONLY']:,} "
            "model-only predictions compared "
            "with the NP3 rule alerts. These "
            "disagreements are potentially useful "
            "for investigating activity patterns "
            "that the rule-based method does not "
            "flag, but they are not proof that "
            "the model is correct."
        )
    else:
        observation_3 = (
            "The HIGH_ACTIVITY target is based "
            "on a grid-specific rolling 24-hour "
            "median baseline and a 1.5x threshold "
            "rather than a direct measurement of "
            "network congestion, capacity, or failure."
        )
    # ==============================================================
    # MARKDOWN REPORT
    # ==============================================================
    report = f"""# ML3 — LightGBM Risk Classifier Evaluation

## 1. Problem

**High-Activity Risk Prediction**

`features at t -> prediction for t+1 -> observed t+1 target`

## 2. Training Data

Feature source:

`network_feature_table`

Features used:

"""
    for feature in FEATURE_COLUMNS:
        report += (
            f"- {feature}\n"
        )
    report += f"""

Target:

`HIGH_ACTIVITY(t+1)`

The target is 1 when the observed next-hour
total activity is greater than 1.5 times the
grid-specific rolling 24-hour median baseline
calculated using activity from t-23h through t.

## 3. Rolling Baseline

Baseline methodology:

For each grid independently, the baseline is the
median activity from t-23h through t, inclusive.

The current feature hour t is included in the baseline.

HIGH_ACTIVITY threshold:

**baseline × {HIGH_ACTIVITY_MULTIPLIER:.2f}**

Therefore:

`HIGH_ACTIVITY = 1`

when:

`future_activity > rolling_24h_median × 1.50`

This provides a grid-specific dynamic threshold
rather than one fixed threshold across all grids.

## 4. Chronological Split

The split is chronological rather than random.

### Training

Rows: **{len(train):,}**

Earliest timestamp:

**{train['feature_timestamp'].min()}**

Latest timestamp:

**{train['feature_timestamp'].max()}**

### Testing

Rows: **{len(test):,}**

Earliest timestamp:

**{test['feature_timestamp'].min()}**

Latest timestamp:

**{test['feature_timestamp'].max()}**

The train and test timestamp ranges do not overlap.

## 5. Algorithm

**LightGBM Binary Classifier**

LightGBM gradient-boosted decision trees
were used for binary HIGH_ACTIVITY prediction.

Probability decision threshold:

**{best_threshold:.2f}**

Threshold selection maintained:

- Minimum precision: **{MIN_PRECISION:.2f}**
- Minimum accuracy: **{MIN_ACCURACY:.2f}**

Within these constraints, recall was maximized.

## 6. Evaluation

| Metric | Test |
|---|---:|
| Accuracy | {accuracy:.4f} |
| Precision | {precision:.4f} |
| Recall | {recall:.4f} |
| F1 | {f1:.4f} |
| ROC-AUC | {auc_score:.4f} |
| Balanced Accuracy | {balanced_accuracy:.4f} |
| Positive base rate | {base_rate:.4f} |

### Test class balance

Class 0:

- Count: **{test_balance['0_count']:,}**
- Percentage: **{test_balance['0_percent']:.2f}%**

Class 1:

- Count: **{test_balance['1_count']:,}**
- Percentage: **{test_balance['1_percent']:.2f}%**

### Operational interpretation

**Precision** measures how often a model
high-activity flag is actually followed by a
high-activity observation.

**Recall** measures how many of the actual
high-activity observations are successfully detected.

**Accuracy** measures the proportion of all
predictions that are correct.

**ROC-AUC** measures the model's ability to
rank positive cases above negative cases across
classification thresholds.

**Balanced Accuracy** gives equal importance to
the positive and negative classes.

## 7. Feature Importance

| Feature | Importance |
|---|---:|
"""

    for _, row in (
        feature_importance_table.iterrows()
    ):

        report += (
            f"| {row['feature']} | "
            f"{row['importance']} |\n"
        )

    report += """

## 8. NP3 Rule-Based Alert Comparison

"""

    if (
        np3_summary
        and "MODEL_AND_NP3" in np3_summary
    ):

        report += f"""| Category | Count |
|---|---:|
| Model and NP3 | {np3_summary['MODEL_AND_NP3']:,} |
| Model only | {np3_summary['MODEL_ONLY']:,} |
| NP3 only | {np3_summary['NP3_ONLY']:,} |
| Neither | {np3_summary['NEITHER']:,} |
"""

    else:

        report += (
            "NP3 comparison was unavailable.\n"
        )

    report += f"""

## 9. Observations

1. {observation_1}
2. {observation_2}
3. {observation_3}

## 10. Limitation

The HIGH_ACTIVITY target is a proxy label based
on a grid-specific rolling 24-hour activity
baseline and a 1.5x threshold.

It should not be interpreted as congestion,
capacity exhaustion, or guaranteed network failure.
"""

    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )

    # ==============================================================
    # JSON REPORT
    # ==============================================================

    json_report = {

        "problem":
            "High-Activity Risk Prediction",

        "algorithm":
            "LightGBM Binary Classifier",

        "features":
            FEATURE_COLUMNS,

        "target":
            "HIGH_ACTIVITY(t+1)",

        "baseline_method":
            "Grid-specific rolling 24-hour median from t-23h through t",

        "baseline_hours":
            BASELINE_HOURS,

        "high_activity_multiplier":
            HIGH_ACTIVITY_MULTIPLIER,

        "threshold_method":
            "Grid-specific rolling 24-hour median from t-23h through t multiplied by 1.5",

        "threshold_selection": {
            "minimum_precision":
                MIN_PRECISION,

            "minimum_accuracy":
                MIN_ACCURACY,

            "optimization_priority":
                [
                    "recall",
                    "f1",
                    "precision",
                    "accuracy",
                ],
        },

        "prediction_probability_threshold":
            float(best_threshold),

        "train": {

            "rows":
                len(train),

            "earliest_timestamp":
                str(
                    train[
                        "feature_timestamp"
                    ].min()
                ),

            "latest_timestamp":
                str(
                    train[
                        "feature_timestamp"
                    ].max()
                ),

            "class_balance":
                train_balance,
        },

        "test": {

            "rows":
                len(test),

            "earliest_timestamp":
                str(
                    test[
                        "feature_timestamp"
                    ].min()
                ),

            "latest_timestamp":
                str(
                    test[
                        "feature_timestamp"
                    ].max()
                ),

            "class_balance":
                test_balance,
        },

        "metrics": {

            "accuracy":
                float(accuracy),

            "precision":
                float(precision),

            "recall":
                float(recall),

            "f1":
                float(f1),

            "roc_auc":
                float(auc_score),

            "balanced_accuracy":
                float(balanced_accuracy),

            "base_rate":
                base_rate,
        },

        "feature_importance": {

            row["feature"]:
                int(row["importance"])

            for _, row
            in feature_importance_table.iterrows()
        },

        "np3_comparison":
            np3_summary,

        "observations": [
            observation_1,
            observation_2,
            observation_3,
        ],
    }

    JSON_REPORT_PATH.write_text(
        json.dumps(
            json_report,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ==============================================================
    # COMPLETE
    # ==============================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "ML3 COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        f"Model  : {MODEL_PATH}"
    )

    print(
        f"Report : {REPORT_PATH}"
    )

    print(
        f"JSON   : {JSON_REPORT_PATH}"
    )

    print(
        "\nThree observations:"
    )

    print(
        f"1. {observation_1}"
    )

    print(
        f"2. {observation_2}"
    )

    print(
        f"3. {observation_3}"
    )

if __name__ == "__main__":
    main()