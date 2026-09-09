# C3 Incident Investigation Report

## Objective

Investigate whether the activity pattern for Grid 4821
has occurred before and determine whether the available data
can be trusted.

The investigation compares:

1. Dump-everything context
2. Curated evidence context
3. Curated evidence with an unhealthy pipeline status

---

## 1. Dump-Everything Experiment

The dump-everything context exceeded Claude's context-window
limit and was recorded as the negative control.

The raw context contained approximately 1.53 million tokens,
while the Claude context limit is 200,000 tokens.

Result:

- Request failed with HTTP 400 BadRequestError.
- The failure was caused by the oversized prompt.
- The failed run is retained as the negative control.

This demonstrates why raw historical evidence should not be
sent directly when it is not necessary for the investigation.

---

## 2. Curated Context Experiment

The curated evidence package contained:

- Current interval activity measures
- Grid features
- Grid location
- Summarized recent history
- Summarized prior alerts
- Current ML risk output
- Current anomaly output
- Pipeline quality and status

The curated investigation completed successfully.

The response was structured into:

- CURRENT EVIDENCE
- HISTORICAL EVIDENCE
- UNCERTAINTY

The model risk and anomaly score were treated as separate
model outputs and were not interpreted as proof of congestion,
capacity problems, or service failure.

---

## 3. Unhealthy Pipeline Experiment

A copy of the curated evidence package was created.

For this controlled sensitivity experiment, the pipeline
health value was changed from healthy to unhealthy.

The actual pipeline and database were not modified.

The purpose was to test whether degraded pipeline health
changes the uncertainty assessment.

### Normal Pipeline Answer

# ANALYSIS FOR GRID 4821

## CURRENT EVIDENCE

**Timestamp:** 2013-11-07 23:00:00

**Activity Metrics:**
- SMS activity: 18.0912
- Call activity: 4.0116
- Internet activity: 232.8647
- Total activity: 254.9675

**Model Outputs:**
- Current model risk: risk_score = 0.0033, risk_level = LOW, model_version = ML3-LightGBM-v1
- Current anomaly: anomaly_score = -0.334, anomaly_direction = NORMAL, anomaly_flag = 0

**Grid Features:**
- Average activity: 360.25
- Activity growth: -2.25%
- Active hours: 24.0
- Peak ratio: 1.85
- Variability: 147.51
- Internet share: 82.67%
- Data quality: STORED, freshness: AVAILABLE

**Location:** Centroid at latitude 45.459, longitude 9.073

## HISTORICAL EVIDENCE

**Recent 7-day period (168 data points from 2013-11-01 00:00:00 to 2013-11-07 23:00:00):**
- Minimum total activity: 119.82
- Maximum total activity: 765.14
- Average total activity: 339.88
- Current total activity (254.97) is below the 7-day average (339.88)
- Current activity falls within the historical range

**Historical risk assessment:**
- Risk score range: 0.0007 to 0.707
- Risk levels: 118 LOW, 3 ATTENTION (out of 168 observations)
- Current risk score (0.0033) is near the lower end of the historical range

**Prior alerts:**
- 1 alert recorded
- Severity: LOW
- Alert timing: 2013-11-07 23:00:00 (same timestamp as current interval)

## UNCERTAINTY

**Pipeline limitations:**
- Pipeline freshness is VERY_STALE (last analytics as of 2013-11-07 23:00:00, but pipeline ran 2026-09-05)
- 1 row rejected during processing (out of 7 rows in)
- The stale analytics significantly limit confidence in whether the current snapshot reflects actual real-time conditions

**Cannot conclude:**
- Whether the below-average activity represents congestion, capacity problems, or service failure
- Whether the negative activity growth (-2.25%) indicates a systematic issue
- What the rejected pipeline row contained or whether it affects this grid's analysis
- Whether conditions have changed since the stale analytics timestamp
- The practical significance of the LOW risk level and NORMAL anomaly direction
- Whether the single LOW severity alert at this timestamp is actionable

The activity measures are unitless and cannot be converted to specific counts or data volumes without additional documentation.

### Unhealthy Pipeline Answer

# INVESTIGATION REPORT: GRID 4821

## CURRENT EVIDENCE

**Timestamp:** 2013-11-07T23:00:00

**Activity Measures:**
- SMS activity: 18.0912
- Call activity: 4.0116
- Internet activity: 232.8647
- Total activity: 254.9675

**Grid Features:**
- Average activity: 360.25
- Activity growth: -2.25%
- Active hours: 24.0
- Peak ratio: 1.85
- Variability: 147.51
- Internet share: 82.67%
- Data quality: STORED
- Freshness: AVAILABLE

**Model Risk Assessment:**
- Risk score: 0.00328
- Risk level: LOW
- Model version: ML3-LightGBM-v1

**Anomaly Detection:**
- Anomaly score: -0.334
- Anomaly direction: NORMAL
- Anomaly flag: 0

**Pipeline Status:**
- Pipeline healthy: **FALSE**
- Rows rejected: 1 (out of 7 rows in)
- Nulls handled: 0
- Freshness: VERY_STALE
- Reason: "C3 sensitivity experiment: pipeline health manually set to unhealthy to test uncertainty handling."

## HISTORICAL EVIDENCE

**Recent History (168 observations from 2013-11-01 to 2013-11-07):**
- Current total activity (254.97) is **below** the historical average (339.88)
- Current activity falls within historical range: minimum 119.82 to maximum 765.14
- Current activity represents 75% of the average historical activity

**Historical Risk Assessment:**
- Historical risk scores ranged from 0.0007 to 0.7072
- Risk level distribution: 118 LOW (70.2%), 3 ATTENTION (1.8%)
- Current risk score (0.00328) is consistent with the historical LOW risk pattern

**Prior Alerts:**
- 1 alert recorded
- Severity: LOW
- Alert timestamp: 2013-11-07T23:00:00 (same as current observation)

The pattern shows moderately lower activity compared to the recent week average, but remains within the observed historical range.

## UNCERTAINTY

**Pipeline Health Compromises Confidence:**
The pipeline is flagged as **unhealthy** due to a deliberate experiment ("C3 sensitivity experiment: pipeline health manually set to unhealthy to test uncertainty handling"). Additionally:
- 1 row was rejected out of 7 input rows (14.3% rejection rate)
- Data freshness is marked as VERY_STALE
- These conditions materially limit confidence in all current metrics

**What Cannot Be Concluded:**
- Whether the activity measures accurately reflect actual network conditions, given the unhealthy pipeline and row rejection
- Whether the low model risk score and normal anomaly detection are reliable, given stale analytics
- Whether capacity is adequate or inadequate—activity measures alone do not indicate capacity status
- Whether any congestion exists—neither the risk model nor anomaly detection output indicates congestion
- Whether service quality is affected—no evidence of service failure is provided
- What the rejected row contained or how its exclusion affects interpretation
- Whether the observed pattern represents operational reality or data pipeline artifacts

The unhealthy pipeline status and stale freshness mean all current evidence should be treated as potentially unreliable until pipeline health is restored and confirmed.

---

## 4. Context Engineering Findings

The dump-everything approach failed because the context was
far larger than the model context window.

The curated approach succeeded because historical evidence
was summarized before being provided to Claude.

The curated package preserved the evidence needed for
investigation while avoiding unnecessary raw historical rows.

Pipeline health also affects the interpretation of the evidence.
When the pipeline is unhealthy, the investigation should place
greater emphasis on data reliability and limitations.

---

## 5. Key Engineering Principles

- Claude reasons from curated evidence.
- Claude does not replace Spark, SQL, ML, or the warehouse.
- Historical rows should be summarized when full raw history
  is unnecessary.
- Current evidence and historical evidence should remain distinct.
- Model outputs should remain distinct from observed activity.
- Pipeline quality is part of the evidence.
- Failed evidence sources must be reported rather than guessed.
- Activity measures must not be interpreted as literal counts or MB.
- Model risk must not automatically be described as congestion.
- Anomaly scores must not automatically be described as congestion.
- Capacity problems and service failures require supporting evidence.
- Uncertainty must be explicitly reported when evidence quality
  is limited.

---

## C3 Status

The C3 long-context incident investigation includes:

- Dump-everything comparison
- Curated-context investigation
- Current model-risk evidence
- Current anomaly evidence
- Historical evidence summarization
- Pipeline-quality assessment
- Unhealthy-pipeline sensitivity experiment
- Context-engineering checklist

