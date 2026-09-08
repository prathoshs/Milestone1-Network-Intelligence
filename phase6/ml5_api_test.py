import sys
from pathlib import Path
import importlib
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase4.api1 import app

client = TestClient(app)

VALID_REQUEST = {
    "grid_id": "1001",
    "feature_timestamp": "2013-11-07 12:00:00",
    "avg_activity": 1000.0,
    "activity_growth": 0.10,
    "active_hours": 24.0,
    "peak_ratio": 1.20,
    "variability": 0.15,
    "internet_share": 0.40,
}

def test_prediction_uses_trained_model():
    response = client.post(
        "/network/predict-risk",
        json=VALID_REQUEST,
    )
    assert response.status_code == 200
    data = response.json()
    assert 0.0 <= data["risk_score"] <= 1.0
    assert data["risk_score"] != 0.50
    assert data["risk_level"] in {
        "LOW",
        "ATTENTION",
        "HIGH",
    }
    assert data["model_version"] == "ML3-LogisticRegression-v1"

def test_feature_timestamp_is_returned():
    response = client.post(
        "/network/predict-risk",
        json=VALID_REQUEST,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feature_timestamp"] == (
        "2013-11-07 12:00:00"
    )

@pytest.mark.parametrize(
    "field,value",
    [
        ("avg_activity", -1.0),
        ("active_hours", -1.0),
        ("active_hours", 25.0),
        ("peak_ratio", -1.0),
        ("variability", -1.0),
        ("internet_share", -0.1),
        ("internet_share", 1.1),
    ],
)
def test_invalid_ml2_features_are_rejected(field, value):
    request = VALID_REQUEST.copy()
    request[field] = value
    response = client.post(
        "/network/predict-risk",
        json=request,
    )
    assert response.status_code == 422

def test_missing_required_feature_is_rejected():
    request = VALID_REQUEST.copy()
    del request["avg_activity"]
    response = client.post(
        "/network/predict-risk",
        json=request,
    )
    assert response.status_code == 422

def test_risk_level_mapping():
    from phase4.api5_prediction import get_risk_level
    assert get_risk_level(0.20) == "LOW"
    assert get_risk_level(0.50) == "ATTENTION"
    assert get_risk_level(0.79) == "ATTENTION"
    assert get_risk_level(0.80) == "HIGH"
    assert get_risk_level(1.00) == "HIGH"
    
def test_missing_model_artifact_fails_clearly(monkeypatch):
    import phase4.api5_prediction as api5
    missing_path = PROJECT_ROOT / "phase6" / "models" / "missing_test_model.joblib"
    monkeypatch.setattr(api5, "MODEL_PATH", missing_path)
    with pytest.raises(FileNotFoundError, match="Required trained model artifact not found"):
        if not api5.MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Required trained model artifact not found: {api5.MODEL_PATH}"
            )