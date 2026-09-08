# ML4 — Anomaly Baseline Evaluation

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

- Grid/hour-of-day buckets: 240,000
- Minimum observations per bucket: 4
- Maximum observations per bucket: 7
- Average observations per bucket: 7.00

The minimum bucket depth is greater than one, confirming that the
ML4 baseline uses more than one day's observations.

## 4. Anomaly Score

The percentage deviation is:

`(current_activity - baseline_activity) / baseline_activity`

Threshold:

`±0.50`

Therefore:

- HIGH = at least 50% above baseline
- LOW = at least 50% below baseline
- NORMAL = within ±50% of baseline

## 5. Anomaly Results

- HIGH anomalies: 83,298
- LOW anomalies: 70,593
- NORMAL observations: 1,526,103

Both high and low anomaly directions are present.

## 6. Three-Way Comparison

Comparison is restricted to the ML3 test population so all three
methods operate on the same grid-hour observations.

| Category | Count |
|---|---:|
| ALL_THREE | 6,060 |
| ML4_NP3 | 6,335 |
| ML4_ML3 | 926 |
| NP3_ML3 | 7,421 |
| ML4_ONLY | 4,146 |
| NP3_ONLY | 81,952 |
| ML3_ONLY | 7,727 |
| NONE | 135,431 |

### Representative disagreement

**Category:** ML4_ONLY

- Grid: 1056
- Timestamp: 2013-11-06 23:00:00
- Activity: 573.74
- Hour-of-day baseline: 371.80
- ML4 anomaly score: 0.5431
- ML4 direction: HIGH
- ML4 anomaly flag: 1
- NP3 alert: 0
- ML3 prediction: 0

The disagreement occurs because ML4 evaluates deviation from the
multi-day hour-of-day historical baseline, while NP3 applies
within-day rule thresholds and ML3 predicts the next hour's
P90-based HIGH_ACTIVITY condition. These methods therefore measure
different aspects of unusual network behavior.


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
