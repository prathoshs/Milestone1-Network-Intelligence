# ML3 — LightGBM Risk Classifier Evaluation

## 1. Problem

**High-Activity Risk Prediction**

`features at t -> prediction for t+1 -> observed t+1 target`

## 2. Training Data

Feature source:

`network_feature_table`

Features used:

- avg_activity
- activity_growth
- peak_ratio
- variability
- internet_share
- current_activity
- previous_hour_activity
- rolling_3h_activity
- rolling_6h_activity
- activity_change
- activity_change_pct


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

**baseline × 1.50**

Therefore:

`HIGH_ACTIVITY = 1`

when:

`future_activity > rolling_24h_median × 1.50`

This provides a grid-specific dynamic threshold
rather than one fixed threshold across all grids.

## 4. Chronological Split

The split is chronological rather than random.

### Training

Rows: **949,991**

Earliest timestamp:

**2013-11-02 23:00:00**

Latest timestamp:

**2013-11-06 21:00:00**

### Testing

Rows: **249,998**

Earliest timestamp:

**2013-11-06 22:00:00**

Latest timestamp:

**2013-11-07 22:00:00**

The train and test timestamp ranges do not overlap.

## 5. Algorithm

**LightGBM Binary Classifier**

LightGBM gradient-boosted decision trees
were used for binary HIGH_ACTIVITY prediction.

Probability decision threshold:

**0.30**

Threshold selection maintained:

- Minimum precision: **0.60**
- Minimum accuracy: **0.90**

Within these constraints, recall was maximized.

## 6. Evaluation

| Metric | Test |
|---|---:|
| Accuracy | 0.9411 |
| Precision | 0.6068 |
| Recall | 0.6900 |
| F1 | 0.6457 |
| ROC-AUC | 0.9524 |
| Balanced Accuracy | 0.8261 |
| Positive base rate | 0.0779 |

### Test class balance

Class 0:

- Count: **230,533**
- Percentage: **92.21%**

Class 1:

- Count: **19,465**
- Percentage: **7.79%**

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
| avg_activity | 1667 |
| current_activity | 1464 |
| variability | 908 |
| previous_hour_activity | 865 |
| peak_ratio | 703 |
| activity_growth | 672 |
| activity_change_pct | 671 |
| internet_share | 630 |
| activity_change | 608 |
| rolling_6h_activity | 534 |
| rolling_3h_activity | 278 |


## 8. NP3 Rule-Based Alert Comparison

| Category | Count |
|---|---:|
| Model and NP3 | 13,481 |
| Model only | 8,653 |
| NP3 only | 88,287 |
| Neither | 139,577 |


## 9. Observations

1. The classifier has recall at least as high as precision, so it captures a relatively larger share of actual high-activity periods than the reliability of its positive predictions.
2. Accuracy is close to the majority-class baseline, so accuracy alone does not demonstrate strong predictive value; precision and recall are more informative.
3. The model produces 8,653 model-only predictions compared with the NP3 rule alerts. These disagreements are potentially useful for investigating activity patterns that the rule-based method does not flag, but they are not proof that the model is correct.

## 10. Limitation

The HIGH_ACTIVITY target is a proxy label based
on a grid-specific rolling 24-hour activity
baseline and a 1.5x threshold.

It should not be interpreted as congestion,
capacity exhaustion, or guaranteed network failure.
