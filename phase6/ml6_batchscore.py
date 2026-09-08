"""
ML6 - Batch Risk Scoring

Reads the ML2 network_feature_table and hourly activity data,
recreates the finalized ML3 temporal features, applies the trained
ML3 LightGBM model to every valid grid/time feature row, and persists
the resulting operational risk scores.
"""

from pathlib import Path
import argparse
import sqlite3
import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)

MODEL_PATH = (
    PROJECT_ROOT
    / "phase6"
    / "models"
    / "ml3_high_activity_lightgbm.joblib"
)

MODEL_VERSION = "ML3-LightGBM-v1"
MODEL_FEATURES = [
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

def get_risk_level(risk_score):
    if risk_score >= 0.80:
        return "HIGH"
    if risk_score >= 0.50:
        return "ATTENTION"
    return "LOW"

def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Required trained model artifact not found: {MODEL_PATH}"
        )
    try:
        model = joblib.load(MODEL_PATH)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load trained model artifact: {MODEL_PATH}"
        ) from exc
    return model

def load_features(conn):
    tables = {
        row[0]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
    }
    if "network_feature_table" not in tables:
        raise RuntimeError(
            "ML6 cannot score: network_feature_table does not exist. "
            "Run ML2 feature generation first."
        )
    features = pd.read_sql_query(
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
        ORDER BY grid_id, feature_timestamp
        """,
        conn,
    )
    if features.empty:
        raise RuntimeError(
            "ML6 cannot score: network_feature_table is empty."
        )
    features["feature_timestamp"] = pd.to_datetime(
        features["feature_timestamp"]
    )
    required = [
        "grid_id",
        "feature_timestamp",
        "avg_activity",
        "activity_growth",
        "peak_ratio",
        "variability",
        "internet_share",
    ]
    missing = [
        column
        for column in required
        if column not in features.columns
    ]
    if missing:
        raise RuntimeError(
            f"ML6 feature table is missing required columns: {missing}"
        )
    return features

def load_hourly_activity(conn):
    tables = {
        row[0]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
    }
    if "fact_network_activity" not in tables:
        raise RuntimeError(
            "ML6 cannot score: fact_network_activity does not exist."
        )
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
        ORDER BY grid_id, event_time
        """,
        conn,
    )
    if activity.empty:
        raise RuntimeError(
            "ML6 cannot score: fact_network_activity is empty."
        )
    activity["timestamp"] = pd.to_datetime(
        activity["timestamp"]
    )
    activity["total_activity"] = pd.to_numeric(
        activity["total_activity"],
        errors="coerce",
    )
    if activity["total_activity"].isnull().any():
        raise RuntimeError(
            "ML6 cannot score: total_activity contains null values."
        )
    return activity

def create_temporal_features(activity):
    """
    Recreate the temporal features used by ML3.

    These are calculated from data available at the current
    timestamp only. No future timestamp is used.
    """
    activity = activity.copy()
    activity = activity.sort_values(
        ["grid_id", "timestamp"]
    ).reset_index(drop=True)
    grouped = activity.groupby(
        "grid_id"
    )["total_activity"]
    activity["current_activity"] = (
        activity["total_activity"]
    )
    activity["previous_hour_activity"] = (
        grouped.shift(1)
    )
    activity["rolling_3h_activity"] = (
        grouped
        .rolling(
            window=3,
            min_periods=3,
        )
        .mean()
        .reset_index(
            level=0,
            drop=True,
        )
    )
    activity["rolling_6h_activity"] = (
        grouped
        .rolling(
            window=6,
            min_periods=6,
        )
        .mean()
        .reset_index(
            level=0,
            drop=True,
        )
    )
    activity["rolling_24h_activity"] = (
        grouped
        .rolling(
            window=24,
            min_periods=24,
        )
        .mean()
        .reset_index(
            level=0,
            drop=True,
        )
    )
    activity["activity_change"] = (
        activity["current_activity"]
        - activity["previous_hour_activity"]
    )
    previous = activity[
        "previous_hour_activity"
    ].replace(0, pd.NA)
    activity["activity_change_pct"] = (
        activity["activity_change"]
        / previous
    )
    activity["activity_change_pct"] = (
        activity["activity_change_pct"]
        .replace(
            [float("inf"), float("-inf")],
            pd.NA,
        )
    )
    return activity

def merge_features(features, activity):
    temporal_columns = [
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
    temporal = activity[
        temporal_columns
    ].copy()
    temporal = temporal.rename(
        columns={
            "timestamp": "feature_timestamp"
        }
    )
    merged = features.merge(
        temporal,
        on=[
            "grid_id",
            "feature_timestamp",
        ],
        how="inner",
        validate="one_to_one",
    )
    if merged.empty:
        raise RuntimeError(
            "ML6 produced no rows after joining ML2 features "
            "with hourly temporal features."
        )
    return merged

def validate_model_features(features):
    missing = [
        column
        for column in MODEL_FEATURES
        if column not in features.columns
    ]
    if missing:
        raise RuntimeError(
            "ML6 is missing model features after temporal "
            f"feature generation: {missing}"
        )
    X = features[
        MODEL_FEATURES
    ].copy()
    if X.isnull().any().any():
        null_counts = X.isnull().sum()
        null_counts = null_counts[
            null_counts > 0
        ].to_dict()
        raise RuntimeError(
            "ML6 cannot score: model features contain null values: "
            f"{null_counts}"
        )
    for column in MODEL_FEATURES:
        if not pd.api.types.is_numeric_dtype(
            X[column]
        ):
            raise RuntimeError(
                "ML6 cannot score: non-numeric model "
                f"feature detected: {column}"
            )
    return X

def validate_model_schema(model):
    """
    Confirm that the loaded model expects the same
    11 features used by finalized ML3.
    """
    if hasattr(model, "feature_name_"):
        model_features = list(
            model.feature_name_
        )
        if model_features != MODEL_FEATURES:
            raise RuntimeError(
                "ML6 model feature schema does not match "
                "the finalized ML3 feature schema.\n"
                f"Expected: {MODEL_FEATURES}\n"
                f"Model:    {model_features}"
            )

def score_features(features, model):
    X = validate_model_features(
        features
    )
    validate_model_schema(
        model
    )
    probabilities = model.predict_proba(
        X
    )[:, 1]
    scores = pd.DataFrame(
        {
            "grid_id": features[
                "grid_id"
            ].astype(str),

            "timestamp": features[
                "feature_timestamp"
            ].dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "risk_score": probabilities.astype(
                float
            ),
            "risk_level": [
                get_risk_level(
                    float(score)
                )
                for score in probabilities
            ],

            "model_version": MODEL_VERSION,
        }
    )
    if scores.duplicated(
        subset=[
            "grid_id",
            "timestamp",
        ]
    ).any():
        raise RuntimeError(
            "ML6 produced duplicate grid/timestamp scores."
        )
    return scores

def persist_scores(scores, conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS network_risk_scores (
            grid_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            risk_score REAL NOT NULL,
            risk_level TEXT NOT NULL,
            model_version TEXT NOT NULL,
            PRIMARY KEY (grid_id, timestamp)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_network_risk_scores_timestamp
        ON network_risk_scores(timestamp)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_network_risk_scores_risk
        ON network_risk_scores(risk_score)
        """
    )
    conn.executemany(
        """
        INSERT INTO network_risk_scores
        (
            grid_id,
            timestamp,
            risk_score,
            risk_level,
            model_version
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(grid_id, timestamp)
        DO UPDATE SET
            risk_score = excluded.risk_score,
            risk_level = excluded.risk_level,
            model_version = excluded.model_version
        """,
        scores.itertuples(
            index=False,
            name=None,
        ),
    )
    conn.commit()

def run(db_path=DB_PATH):
    print("=" * 70)
    print("ML6 - Batch Risk Scoring")
    print("=" * 70)
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Warehouse database not found: {db_path}"
        )
    print(
        "Model:",
        MODEL_PATH.name,
    )
    print(
        "Model version:",
        MODEL_VERSION,
    )
    model = load_model()
    conn = sqlite3.connect(
        db_path
    )
    try:
        features = load_features(
            conn
        )
        print(
            f"Feature rows read: {len(features):,}"
        )
        print(
            "Feature timestamp range:",
            features[
                "feature_timestamp"
            ].min(),
            "to",
            features[
                "feature_timestamp"
            ].max(),
        )
        activity = load_hourly_activity(
            conn
        )
        print(
            f"Hourly activity rows read: {len(activity):,}"
        )
        activity = create_temporal_features(
            activity
        )
        features = merge_features(
            features,
            activity,
        )
        print(
            "Rows after temporal feature join:",
            f"{len(features):,}",
        )
        scores = score_features(
            features,
            model,
        )
        persist_scores(
            scores,
            conn,
        )
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_risk_scores
            """
        ).fetchone()[0]
        duplicates = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    grid_id,
                    timestamp
                FROM network_risk_scores
                GROUP BY
                    grid_id,
                    timestamp
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        high_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_risk_scores
            WHERE risk_level = 'HIGH'
            """
        ).fetchone()[0]
        attention_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_risk_scores
            WHERE risk_level = 'ATTENTION'
            """
        ).fetchone()[0]
        low_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM network_risk_scores
            WHERE risk_level = 'LOW'
            """
        ).fetchone()[0]
        print(f"Risk scores written: {len(scores):,}")
        print(f"Total risk-score rows: {count:,}")
        print(f"HIGH risk rows: {high_count:,}")
        print(f"ATTENTION risk rows: {attention_count:,}")
        print(f"LOW risk rows: {low_count:,}")
        print(f"Duplicate grid/timestamp groups: {duplicates}")
        print(
            "Model features:",
            ", ".join(MODEL_FEATURES),
        )
        print("ML6 batch scoring completed successfully.")
        return scores
    finally:
        conn.close()

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