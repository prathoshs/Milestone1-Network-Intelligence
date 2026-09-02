from fastapi import APIRouter,FastAPI
from pydantic import BaseModel, Field

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
    explanation_note: str

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
    # --------------------------------------------------------
    # STUB IMPLEMENTATION
    # --------------------------------------------------------
    return PredictionResponse(
        risk_score=0.50,
        risk_level="ATTENTION",
        model_version="STUB-v1",
        explanation_note=(
            "Prediction implementation is currently a stub. "
            "No trained ML model is being used."
        ),
    )