# API5 Prediction Contract

## Endpoint

POST /network/predict-risk

## Request

The request must contain:

- grid_id
- feature_timestamp
- avg_activity
- activity_growth
- active_hours
- peak_ratio
- variability
- internet_share

## Response

The response contains:

- risk_score
- risk_level
- model_version
- explanation_note

## Current Implementation

The current implementation is a stub.

model_version is:

STUB-v1

No trained ML model is used.

## Future ML5 Compatibility

ML5 must preserve this request and response contract.

The trained model may replace the stub implementation without
requiring a change to the API contract or its consumers.