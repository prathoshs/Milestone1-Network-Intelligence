# ML6 Top-20 Operational Attention Report

## Purpose

This report identifies the twenty grid-time observations with the highest model-based operational attention scores.

**Important:** The risk score represents the ML3 LightGBM model's probability of HIGH_ACTIVITY in the next hour. It is not a direct prediction of congestion, capacity failure, or service failure.

## Top 20 Operational Attention

| Rank | Grid | Timestamp | Risk Score | Attention Level | Reason |
|---:|---|---|---:|---|---|
| 1 | 7052 | 2013-11-04 10:00:00 | 0.995912 | HIGH | High next-hour activity attention; avg activity=793.70, activity growth=1.60, peak ratio=9.77, variability=1511.24, internet share=81.42% |
| 2 | 2529 | 2013-11-04 10:00:00 | 0.995490 | HIGH | High next-hour activity attention; avg activity=41.89, activity growth=1.26, peak ratio=5.67, variability=57.62, internet share=70.70% |
| 3 | 5773 | 2013-11-04 09:00:00 | 0.995223 | HIGH | High next-hour activity attention; avg activity=1106.45, activity growth=1.28, peak ratio=7.73, variability=1861.71, internet share=83.66% |
| 4 | 7052 | 2013-11-04 11:00:00 | 0.994962 | HIGH | High next-hour activity attention; avg activity=1110.96, activity growth=2.59, peak ratio=7.23, variability=2087.49, internet share=83.56% |
| 5 | 46 | 2013-11-04 10:00:00 | 0.994760 | HIGH | High next-hour activity attention; avg activity=71.29, activity growth=1.01, peak ratio=6.23, variability=104.03, internet share=83.73% |
| 6 | 45 | 2013-11-04 10:00:00 | 0.994760 | HIGH | High next-hour activity attention; avg activity=71.29, activity growth=1.01, peak ratio=6.23, variability=104.03, internet share=83.73% |
| 7 | 44 | 2013-11-04 10:00:00 | 0.994760 | HIGH | High next-hour activity attention; avg activity=71.29, activity growth=1.01, peak ratio=6.23, variability=104.03, internet share=83.73% |
| 8 | 5773 | 2013-11-04 10:00:00 | 0.994494 | HIGH | High next-hour activity attention; avg activity=1522.38, activity growth=2.23, peak ratio=6.86, variability=2627.83, internet share=83.47% |
| 9 | 5773 | 2013-11-04 12:00:00 | 0.994368 | HIGH | High next-hour activity attention; avg activity=2459.79, activity growth=4.34, peak ratio=5.12, variability=3847.58, internet share=82.98% |
| 10 | 46 | 2013-11-04 11:00:00 | 0.994342 | HIGH | High next-hour activity attention; avg activity=91.65, activity growth=1.50, peak ratio=6.10, variability=142.49, internet share=83.94% |
| 11 | 45 | 2013-11-04 11:00:00 | 0.994342 | HIGH | High next-hour activity attention; avg activity=91.65, activity growth=1.50, peak ratio=6.10, variability=142.49, internet share=83.94% |
| 12 | 44 | 2013-11-04 11:00:00 | 0.994342 | HIGH | High next-hour activity attention; avg activity=91.65, activity growth=1.50, peak ratio=6.10, variability=142.49, internet share=83.94% |
| 13 | 7152 | 2013-11-04 11:00:00 | 0.994212 | HIGH | High next-hour activity attention; avg activity=436.59, activity growth=1.64, peak ratio=6.26, variability=708.54, internet share=83.99% |
| 14 | 5504 | 2013-11-04 11:00:00 | 0.994178 | HIGH | High next-hour activity attention; avg activity=13.45, activity growth=0.44, peak ratio=2.75, variability=9.37, internet share=80.69% |
| 15 | 5773 | 2013-11-04 11:00:00 | 0.994090 | HIGH | High next-hour activity attention; avg activity=1958.80, activity growth=3.20, peak ratio=5.61, variability=3226.48, internet share=83.07% |
| 16 | 4574 | 2013-11-04 08:00:00 | 0.994075 | HIGH | High next-hour activity attention; avg activity=80.35, activity growth=0.86, peak ratio=3.88, variability=101.44, internet share=32.72% |
| 17 | 2366 | 2013-11-04 11:00:00 | 0.994057 | HIGH | High next-hour activity attention; avg activity=378.44, activity growth=1.91, peak ratio=4.91, variability=536.33, internet share=80.06% |
| 18 | 7151 | 2013-11-04 09:00:00 | 0.994040 | HIGH | High next-hour activity attention; avg activity=108.80, activity growth=1.10, peak ratio=6.87, variability=170.28, internet share=80.70% |
| 19 | 1543 | 2013-11-04 12:00:00 | 0.994037 | HIGH | High next-hour activity attention; avg activity=80.68, activity growth=1.35, peak ratio=4.01, variability=99.07, internet share=84.02% |
| 20 | 1542 | 2013-11-04 12:00:00 | 0.994037 | HIGH | High next-hour activity attention; avg activity=81.67, activity growth=1.32, peak ratio=4.00, variability=99.82, internet share=82.52% |

## Model Information

Model version: `ML3-LightGBM-v1`

Model type: `LightGBM Binary Classifier`

Prediction target: `HIGH_ACTIVITY` in the next hour

Model features:

- `avg_activity`
- `activity_growth`
- `peak_ratio`
- `variability`
- `internet_share`
- `current_activity`
- `previous_hour_activity`
- `rolling_3h_activity`
- `rolling_6h_activity`
- `activity_change`
- `activity_change_pct`

## Operational Interpretation

These observations are operational attention candidates. Higher scores indicate that the trained ML3 LightGBM model assigns a higher probability to HIGH_ACTIVITY in the following hour.

The feature values provide context for prioritization. They do not by themselves establish congestion, a capacity failure, or a service failure.

The ranking is based on the persisted ML6 risk scores generated from the finalized ML3 LightGBM model.