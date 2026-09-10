# Project Slash Commands

These five slash commands implement common diagnostic and review operations for the Network Intelligence project.

All commands are implemented in `phase7/commands.py` with CLI wrappers in `phase7/cmd_*.py`.

---

## `/check-pipeline`

**Purpose:** Monitor pipeline health, data staleness, and rejection tracking.

**Input Parameters:**
- `--as-of` (optional): ISO-8601 timestamp; defaults to latest available

**Tools Called:**
- SQLite warehouse query on `fact_network_activity`
- Query on `rejected_records` table

**Output Format:**
```
{
  "status": "healthy|warning|failure",
  "last_run": "ISO-8601 timestamp",
  "max_available_timestamp": "ISO-8601",
  "staleness_hours": float,
  "warehouse_rows": int,
  "rejected_rows": int,
  "rejected_reasons": [str],
  "components": [
    {"name": str, "status": str}
  ]
}
```

**Interpretation:**
- **healthy**: Last data < 24 hours old, no rejections
- **warning**: Last data < 72 hours old or minor rejections
- **failure**: Data stale (> 72h) or significant issues

**Usage:**
```bash
python phase7/cmd_check_pipeline.py
python phase7/cmd_check_pipeline.py --as-of "2013-11-04 15:00:00"
```

---

## `/explain-grid`

**Purpose:** Comprehensive grid analysis combining activity, features, risk, and anomaly data.

**Input Parameters:**
- `GRID_ID` (required): integer grid identifier
- `--as-of` (optional): ISO-8601 reporting timestamp

**Tools Called:**
- SQLite `fact_network_activity` for current and baseline activity
- SQLite `network_risk_scores` for ML risk
- SQLite `anomaly_scores` for baseline deviation
- GeoJSON `milano-grid.geojson` for location lookup

**Output Format:**
```
{
  "grid_id": int,
  "timestamp": str,
  "severity": "high|medium|low",
  "severity_reason": str,
  "evidence": {
    "current_activity": float,
    "baseline_activity": float,
    "activity_ratio": float,
    "ml_risk_score": float | null,
    "anomaly_score": float | null,
    "location": {
      "lat": float,
      "lng": float,
      "description": str
    }
  },
  "interpretation": str,
  "next_checks": [str, ...]
}
```

**Output Sections:**

1. **SEVERITY** — Assigned based on:
   - Activity ratio vs baseline (>1.5x = high, >1.2x = medium)
   - ML risk score (>0.7 = high, >0.4 = medium)

2. **EVIDENCE** — Observed data points:
   - Current and baseline activity with ratio
   - ML and anomaly scores if available
   - Geographic coordinates

3. **INTERPRETATION** — Reasoned analysis:
   - Compare activity to baseline
   - ML model assessment
   - No claim of confirmed congestion

4. **NEXT CHECKS** — Recommended investigations:
   - Data quality validation
   - Correlated grid analysis
   - Further investigation areas

**Usage:**
```bash
python phase7/cmd_explain_grid.py 4821
python phase7/cmd_explain_grid.py 4821 --as-of "2013-11-04 15:00:00"
```

---

## `/review-anomaly`

**Purpose:** Compare rule-based alerts, ML classifier output, and anomaly scores; identify disagreement.

**Input Parameters:**
- `GRID_ID` (required): integer grid identifier
- `TIMESTAMP` (required): ISO-8601 datetime

**Tools Called:**
- SQLite `fact_network_activity` for activity and baseline
- SQLite `network_risk_scores` for ML prediction
- SQLite `anomaly_scores` for baseline deviation

**Output Format:**
```
{
  "grid_id": int,
  "timestamp": str,
  "rule_alert": {
    "triggered": bool,
    "reason": str
  },
  "classifier": {
    "prediction": bool | null,
    "probability": float | null
  },
  "anomaly": {
    "score": float | null,
    "direction": "above_baseline|below_baseline|neutral"
  },
  "agreement": bool | null,
  "disagreement_analysis": str,
  "reconciliation": str
}
```

**Logic:**

- **Rule Alert**: Triggered if current_activity > baseline × 1.5 (NP3 HIGH_ACTIVITY)
- **ML Classifier**: Prediction = True if risk_score > 0.5 (trained Logistic Regression)
- **Anomaly**: Score = deviation from historical baseline (direction: above/below)
- **Agreement**: All three signals align
- **Disagreement**: Analyzed if predictions conflict

**Usage:**
```bash
python phase7/cmd_review_anomaly.py 4821 "2013-11-04 15:00:00"
```

---

## `/test-api`

**Purpose:** Execute the FastAPI test suite and summarize pass/fail status.

**Input Parameters:** None

**Tools Called:**
- Bash: `pytest phase4/ -v --tb=short`

**Output Format:**
```
{
  "status": "passed|failed|error",
  "total_tests": int,
  "passed": int,
  "failed": int,
  "errors": [
    {
      "test": str,
      "message": str
    }
  ],
  "execution_time": float,
  "output_excerpt": str
}
```

**Interpretation:**
- **passed**: All tests pass, API contracts valid
- **failed**: One or more tests failed, see error details
- **error**: Test execution failed (environment, missing deps, etc.)

**Output Sections:**
- Test count summary
- Up to 10 failed test details
- Last 500 chars of pytest output for diagnostics

**Usage:**
```bash
python phase7/cmd_test_api.py
```

---

## `/network-health`

**Purpose:** Validate data grain integrity on the fact table (should be unique on grid_id, timestamp).

**Input Parameters:** None

**Tools Called:**
- SQLite query with GROUP BY to detect grain violations

**Output Format:**
```
{
  "status": "PASS|FAIL|ERROR",
  "table": "fact_network_activity",
  "total_rows": int,
  "duplicates_found": int,
  "grain_validation": {
    "expected_grain": "(grid_id, timestamp)",
    "duplicate_rows": [
      {
        "grid_id": int,
        "timestamp": str,
        "count": int
      }
    ],
    "validation_passed": bool
  },
  "recommendation": str
}
```

**Interpretation:**

- **PASS**: No duplicates; grain is valid
- **FAIL**: Duplicate (grid_id, timestamp) rows found; data quality issue
- **ERROR**: Query execution failure

**Output Sections:**
- Row counts and duplicate detection
- List of violating (grid_id, timestamp) pairs
- Recommendation for remediation

**Usage:**
```bash
python phase7/cmd_network_health.py
```

---

## Implementation Notes

### Database Schema Assumptions

Commands assume standard warehouse schema:
- `fact_network_activity(grid_id, timestamp, total_activity, ...)`
- `network_risk_scores(grid_id, timestamp, risk_score)`
- `anomaly_scores(grid_id, timestamp, anomaly_score)`
- `rejected_records(reason, ...)`

Inspect `phase3/de6_warehousemodel.py` for actual schema.

### GeoJSON Reference

- Location lookup uses `milano-grid.geojson`
- Matches `grid_id` to `feature.properties.cellId`
- Returns lat/lng or None if not found

### Time Filtering

All commands respect the `as_of` parameter to enable historical queries. Default is max available timestamp.

### Baseline Calculation

- 7-day rolling average of `total_activity` before the query timestamp
- Excludes the current timestamp itself
- Handles null/zero values gracefully

### Terminology

All output respects project CLAUDE.md terminology:
- Activity, not SMS/call/throughput counts
- High-activity risk, not confirmed congestion
- Anomaly, not outage
- Model prediction, not proven threat

---

## Integration with Claude Code

These commands can be invoked:

1. **Directly**: `python phase7/cmd_*.py [args]`
2. **From Claude Code**: Via Bash tool
3. **In scripts**: Import `phase7.commands` and call functions directly

Example integration in Claude Code:
```python
from phase7.commands import explain_grid
result = explain_grid(grid_id=4821)
print(result['interpretation'])
```

---

## Error Handling

All commands:
- Gracefully handle missing data (return status=no_data)
- Catch database errors (return status=error with message)
- Default null values for unavailable signals
- Continue with available evidence if some data is missing

Exit codes:
- 0: Success / PASS
- 1: Failure / FAIL / Error
