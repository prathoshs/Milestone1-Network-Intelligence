from pathlib import Path
import sqlite3
import joblib
import pandas as pd
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

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
MODEL_VERSION = "ML3-LightGBM-v1"

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Required trained model artifact not found: {MODEL_PATH}"
    )
try:
    MODEL = joblib.load(MODEL_PATH)
except Exception as exc:
    raise RuntimeError(
        f"Failed to load trained model artifact: {MODEL_PATH}"
    ) from exc

# ============================================================
# PYDANTIC REQUEST MODEL
# ============================================================
class PredictionRequest(BaseModel):
    grid_id: str
    feature_timestamp: str
    avg_activity: float = Field(..., ge=0)
    activity_growth: float
    active_hours: float = Field(..., ge=0, le=24)
    peak_ratio: float = Field(..., ge=0)
    variability: float = Field(..., ge=0)
    internet_share: float = Field(..., ge=0, le=1)

# ============================================================
# PYDANTIC RESPONSE MODEL
# ============================================================
class PredictionResponse(BaseModel):
    risk_score: float
    risk_level: str
    model_version: str
    feature_timestamp: str
    explanation_note: str

def get_risk_level(risk_score: float) -> str:
    if risk_score >= 0.80:
        return "HIGH"
    if risk_score >= 0.50:
        return "ATTENTION"
    return "LOW"
# ============================================================
# LOAD TEMPORAL FEATURES
# ============================================================
def load_temporal_features(
    grid_id: str,
    feature_timestamp: str,
) -> dict:
    timestamp = pd.Timestamp(feature_timestamp)
    with sqlite3.connect(DB_PATH) as conn:
        query = """
            SELECT
                event_time AS timestamp,
                (
                    COALESCE(sms_count, 0)
                    + COALESCE(call_count, 0)
                    + COALESCE(internet_volume, 0)
                ) AS total_activity
            FROM fact_network_activity
            WHERE grid_id = ?
            ORDER BY event_time
        """
        rows = conn.execute(
            query,
            (grid_id,),
        ).fetchall()
    if not rows:
        raise ValueError(
            f"No activity history found for grid_id={grid_id}"
        )
    activity = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "total_activity",
        ],
    )
    activity["timestamp"] = pd.to_datetime(
        activity["timestamp"]
    )
    activity = activity.sort_values(
        "timestamp"
    ).reset_index(drop=True)
    matching = activity[
        activity["timestamp"] == timestamp
    ]
    if matching.empty:
        raise ValueError(
            f"No activity record found for "
            f"grid_id={grid_id}, "
            f"timestamp={feature_timestamp}"
        )
    idx = matching.index[0]
    current_activity = float(
        activity.loc[idx, "total_activity"]
    )
    previous_hour_activity = 0.0
    previous_rows = activity[
        activity["timestamp"]
        == timestamp - pd.Timedelta(hours=1)
    ]
    if not previous_rows.empty:
        previous_hour_activity = float(
            previous_rows.iloc[0]["total_activity"]
        )
    recent_3h = activity[
        (activity["timestamp"] >= timestamp - pd.Timedelta(hours=2))
        & (activity["timestamp"] <= timestamp)
    ]["total_activity"]
    recent_6h = activity[
        (activity["timestamp"] >= timestamp - pd.Timedelta(hours=5))
        & (activity["timestamp"] <= timestamp)
    ]["total_activity"]
    rolling_3h_activity = float(
        recent_3h.mean()
    )
    rolling_6h_activity = float(
        recent_6h.mean()
    )
    activity_change = (
        current_activity
        - previous_hour_activity
    )
    if previous_hour_activity != 0:
        activity_change_pct = (
            activity_change
            / previous_hour_activity
        )
    else:
        activity_change_pct = 0.0
    return {
        "current_activity": current_activity,
        "previous_hour_activity": previous_hour_activity,
        "rolling_3h_activity": rolling_3h_activity,
        "rolling_6h_activity": rolling_6h_activity,
        "activity_change": activity_change,
        "activity_change_pct": activity_change_pct,
    }
# ============================================================
# FASTAPI APPLICATION
# ============================================================
router = APIRouter()
app = FastAPI(
    title="Milestone 1 Network Intelligence API",
    version="1.0.0",
)
app.include_router(router)
# ============================================================
# API5 — PREDICTION ENDPOINT
# ============================================================
@router.post(
    "/network/predict-risk",
    response_model=PredictionResponse,
    summary="Predict network risk",
)
def predict_risk(
    request: PredictionRequest,
) -> PredictionResponse:
    temporal_features = load_temporal_features(
        request.grid_id,
        request.feature_timestamp,
    )
    features = pd.DataFrame(
        [
            {
                "avg_activity": request.avg_activity,
                "activity_growth": request.activity_growth,
                "peak_ratio": request.peak_ratio,
                "variability": request.variability,
                "internet_share": request.internet_share,
                "current_activity":
                    temporal_features[
                        "current_activity"
                    ],
                "previous_hour_activity":
                    temporal_features[
                        "previous_hour_activity"
                    ],
                "rolling_3h_activity":
                    temporal_features[
                        "rolling_3h_activity"
                    ],

                "rolling_6h_activity":
                    temporal_features[
                        "rolling_6h_activity"
                    ],
                "activity_change":
                    temporal_features[
                        "activity_change"
                    ],
                "activity_change_pct":
                    temporal_features[
                        "activity_change_pct"
                    ],
            }
        ],
        columns=MODEL_FEATURES,
    )
    risk_score = float(
        MODEL.predict_proba(features)[0][1]
    )
    risk_level = get_risk_level(
        risk_score
    )
    return PredictionResponse(
        risk_score=risk_score,
        risk_level=risk_level,
        model_version=MODEL_VERSION,
        feature_timestamp=request.feature_timestamp,
        explanation_note=(
            "Risk score is the trained ML3 LightGBM "
            "probability of HIGH_ACTIVITY in the next hour."
        ),
    )