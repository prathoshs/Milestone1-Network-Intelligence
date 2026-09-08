# ML1 — Operational ML Problem Definition

## 1. Purpose

The goal of Phase 6 is to add lightweight, explainable machine-learning intelligence to the existing Network Intelligence Project.

The ML system will use historical network activity to estimate whether a grid is likely to experience **high activity in the next hourly time window**.

The model is intended to support **human investigation**, not to claim that the network is congested or experiencing a confirmed fault.

---

## 2. Candidate ML Problems

Three possible operational ML problems were considered:

### A. High-Activity Risk Prediction

Predict whether a grid will have unusually high activity in the next hour.

**Advantages:**

* Directly related to existing network activity data.
* Can use the existing hourly summaries and engineered features.
* Easy to explain.
* Supports proactive investigation.

### B. Activity Anomaly Detection

Identify activity patterns that differ significantly from historical behavior.

**Advantages:**

* Useful for detecting unusual behavior.
* Can be developed later as a secondary intelligence capability.

### C. Activity-Drop Prediction

Predict whether a grid will experience an unusually large decrease in activity in the next hour.

**Advantages:**

* Could help identify grids requiring investigation.
* Useful as a complementary signal.

---

# 3. Selected Primary Problem

## High-Activity Risk Prediction

The primary ML problem for Phase 6 is:

> **Predict whether a grid is likely to experience high network activity during the next hourly time window.**

The prediction is based only on information available up to the current time window.

The model will produce a risk score and risk level that can be used to decide whether a human operator should investigate the grid.

---

# 4. Prediction Unit

The prediction unit is:

> **One grid (`grid_id`) + one hourly time window**

For every grid and hourly timestamp `t`, the system calculates features using historical activity up to and including `t`.

The model then predicts the target for the **next hour (`t+1`)**.

---

# 5. Time Boundary

The most important ML boundary is:

```text
DATA THROUGH t
      ↓
FEATURE ENGINEERING
      ↓
MODEL
      ↓
PREDICTION FOR t+1
      ↓
OBSERVED t+1
      ↓
TARGET / LABEL
```

### Feature window

Features are calculated using observations available through time `t`.

### Target window

The target describes activity during the future hourly window `t+1`.
Therefore:

```text
Features → trailing history ending at t
Target   → future hour t+1
```

The target must **never describe the same time window used to calculate the features**.

---

# 6. Feature Contract

The following six features will be used initially.

| Feature           | Meaning                                                       |
| ----------------- | ------------------------------------------------------------- |
| `avg_activity`    | Average total activity during the trailing historical window  |
| `activity_growth` | Recent activity growth compared with the previous period      |
| `active_hours`    | Number of active hours in the trailing window                 |
| `peak_ratio`      | Relationship between peak activity and typical activity       |
| `variability`     | Degree of variation in recent activity                        |
| `internet_share`  | Proportion of total activity contributed by internet activity |

These features describe the recent behavior of the grid.

They do not contain information from the future target window.

---

# 7. Target / Label Definition

The target is a binary classification label.

```text
HIGH_ACTIVITY = 1
HIGH_ACTIVITY = 0
```

For each grid at time `t`:

```text
target(t) = 1
if total activity during t+1 > historical high-activity threshold

target(t) = 0
otherwise
```

The threshold will initially be defined as the **90th percentile of historical total activity**.

---

# 8. Proxy Label

The `HIGH_ACTIVITY` target is a **synthetic training proxy**.

It means:

> The future activity level is unusually high compared with the historical activity distribution.

It does **not** mean:

* the network is congested
* the network has exceeded capacity
* throughput is insufficient
* a network failure has occurred
* a fault is confirmed

The threshold and proxy-label strategy must be documented and kept separate from real operational fault labels.

---

# 9. Allowed ML Claims

The model is allowed to claim:

* a grid has a higher predicted probability of high activity in the next hour
* a grid has elevated activity risk
* recent activity patterns indicate increased future high-activity risk
* a grid should be investigated based on the model output

The model provides a **risk signal**, not a confirmed operational diagnosis.

---

# 10. Forbidden Claims / Non-Goals

The model must **not** claim that:

* the network is congested
* the grid has insufficient capacity
* throughput is inadequate
* a fault or failure is guaranteed
* the network will definitely experience a problem
* capacity utilization has been measured

The current dataset does not provide the required capacity, throughput, latency, packet-loss, or utilization information needed to make those claims.

---

# 11. Business Action

The model's output should lead to a human investigation action.

### Approved business action

> **Investigate the grid and review its recent activity pattern.**

The model should not automatically conclude that a grid is congested or faulty.

---

# 12. Leakage Risks

Data leakage must be explicitly prevented.

### Risk 1 — Using t+1 activity as a feature

The activity from the future target window must not be included in the feature calculation.

### Risk 2 — Same-window target

The target must describe `t+1`, not the same window `t`.

Incorrect:

```text
Features from t → Target from t
```

Correct:

```text
Features from data through t → Target from t+1
```

### Risk 3 — Future-derived aggregates

Historical statistics used for features or thresholds must not accidentally include observations from the future relative to the prediction timestamp.

### Risk 4 — Random train/test split

A random split can allow future patterns to influence the training set while earlier observations are placed in the test set.

ML3 will therefore use a **chronological/time-aware split**.

### Risk 5 — Threshold leakage

The high-activity threshold must be calculated using the appropriate historical training period rather than information from future evaluation periods.

---

# 13. Model Input / Output Concept

For every:

```text
grid_id + timestamp t
```
the model receives:

```text
avg_activity
activity_growth
active_hours
peak_ratio
variability
internet_share
```

and produces a prediction for:

```text
HIGH_ACTIVITY during t+1
```

The eventual API will expose this prediction as a risk score and risk level.

---

# 14. Expected ML Pipeline

The planned Phase 6 storyline is:

```text
Historical Network Activity
          ↓
Hourly Summaries
          ↓
Feature Engineering
          ↓
Time-Aware Training Data
          ↓
Simple Explainable Model
          ↓
High-Activity Risk Score
          ↓
Risk Level
          ↓
API
          ↓
Network Intelligence Dashboard
```

---

# 15. ML1 Acceptance Checklist

| Requirement                                     | Status |
| ----------------------------------------------- | ------ |
| Primary ML problem selected                     | PASS   |
| Prediction unit defined                         | PASS   |
| Grid + hourly time window defined               | PASS   |
| Features defined                                | PASS   |
| Target defined                                  | PASS   |
| Target represents future `t+1` window           | PASS   |
| Exact t/t+1 boundary defined                    | PASS   |
| Synthetic proxy label documented                | PASS   |
| 90th percentile threshold selected              | PASS   |
| Congestion claim explicitly forbidden           | PASS   |
| Capacity/throughput claims explicitly forbidden | PASS   |
| Human investigation action defined              | PASS   |
| Leakage risks identified                        | PASS   |
| Time-aware validation requirement identified    | PASS   |

---

# 16. ML1 Final Decision

**Primary problem:** High-activity risk prediction
**Prediction unit:** `grid_id + hourly time window`
**Features:** Trailing historical features ending at `t`
**Target:** High activity during future hour `t+1`
**Threshold:** Historical 90th percentile
**Label type:** Synthetic proxy
**Business action:** Investigate the grid and review its recent activity pattern.
**Non-goals:** Congestion, capacity, throughput, guaranteed fault/failure.
**Validation principle:** Chronological/time-aware validation to prevent leakage.