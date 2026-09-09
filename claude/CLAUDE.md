# CLAUDE.md — Milestone1 Network Intelligence Project Rules

## Purpose

This file defines the canonical architecture, data semantics, terminology,
and safety rules for the Milestone1 Network Intelligence project.

These rules are owned and approved by the learner. Claude Code must follow
them when inspecting, modifying, testing, or explaining this repository.

Do not replace these project rules with assumptions about generic telecom,
network, customer, tower, or capacity systems.

---

# 1. Canonical Data Schema and Grain

## Raw / Canonical Grain

The supplied Milan telecom CSV files contain activity at:

    timestamp + grid_id + country_code

The original raw column names are mapped to the project canonical names:

    datetime    -> timestamp
    CellID      -> grid_id
    countrycode -> country_code
    smsin       -> sms_in
    smsout      -> sms_out
    callin      -> call_in
    callout     -> call_out
    internet    -> internet_activity

One raw/canonical row represents one hourly activity record for a
geographic grid and one country-code category.

Multiple rows can therefore exist for the same grid and hourly timestamp
because country_code is part of the raw/canonical grain.

Country-code detail must be preserved in the raw/canonical layer when
available.

## Main Analytics Grain

The operational analytics grain is:

    one grid_id per hourly timestamp

Country-code rows are aggregated before the main operational analytics path.

The five activity measures are summed across country_code:

    sms_in
    sms_out
    call_in
    call_out
    internet_activity

The resulting analytics data has exactly one logical record for:

    (grid_id, timestamp)

This grain is the canonical downstream analytics grain.

Never introduce country_code into the main operational analytics grain,
warehouse fact grain, API reporting, ML features, or dashboard reporting
unless a separate explicitly approved analysis requires it.

Always verify the physical database schema before writing SQL. Do not
assume that logical names such as timestamp/grid_id are identical to every
physical warehouse column name.

---

# 2. Activity Values Are Proportional Activity Measures

The SMS, call, and internet fields are activity measures from the supplied
Milan telecom dataset.

They are NOT:

- SMS message counts
- call connection counts
- subscriber counts
- customer counts
- call minutes
- megabytes
- gigabytes
- network throughput
- network capacity
- utilization

Use terminology such as:

- SMS activity
- call activity
- internet activity
- activity intensity
- total activity
- high activity
- activity increase
- activity decrease

Do not convert activity values into units that are not present in the
dataset.

`total_activity` is a project-defined composite activity indicator. It is
not an official telecom KPI.

Never write explanations such as:

    "5,000 SMS messages"
    "300 MB of traffic"
    "500 calls per hour"

unless a separately verified source actually provides those units.

---

# 3. High Activity Must Never Be Described as Confirmed Congestion

This project measures communication activity, not radio capacity,
network utilization, throughput, latency, packet loss, or service
availability.

Therefore:

    high activity != confirmed congestion

A hotspot, alert, anomaly, or ML risk score is an operational attention
signal for investigation.

It is NOT proof of:

- congestion
- capacity exhaustion
- infrastructure failure
- service failure
- outage

Forbidden conclusions include:

    "Grid 4821 is congested."
    "The network is at capacity."
    "A service failure was detected."
    "The grid has a confirmed outage."

Preferred wording includes:

    "Grid 4821 shows high activity."

    "Grid 4821 has elevated activity relative to its baseline."

    "The model predicts elevated high-activity risk."

    "An activity anomaly was detected."

    "This grid is an operational attention candidate."

    "Further investigation is recommended."

If congestion is ever discussed, it must be explicitly identified as a
proxy, simulation, or hypothetical interpretation and must not be stated
as an observed fact.

---

# 4. Distinguish Rules, Features, Anomalies, and ML Risk

Do not treat all high-activity-related concepts as identical.

## NP3 Alerts

NP3 contains rule-based operational alert logic.

Relevant concepts include:

- HIGH_ACTIVITY
- ACTIVITY_SPIKE
- ACTIVITY_DROP
- baseline comparisons

These are rule-based activity signals.

## ML2 Features

ML2 creates network activity features such as:

- avg_activity
- activity_growth
- active_hours
- peak_ratio
- variability
- internet_share

Feature calculations must not use future information beyond the feature
timestamp.

## ML3 Prediction

ML3 is the high-activity prediction model.

It uses chronological training/testing and predicts whether the next
hour is likely to meet the project-defined high-activity condition.

The ML3 implementation uses Logistic Regression with StandardScaler.

Do not describe ML3 as a congestion classifier.

Do not describe ML3 as a service-failure predictor.

## ML4 Anomaly Analysis

ML4 performs anomaly analysis using a historical baseline.

Anomaly score direction matters:

- positive = activity above baseline
- negative = activity below baseline
- magnitude = relative deviation from baseline

A negative anomaly score does NOT mean negative activity.

An anomaly classification must be interpreted according to the actual
ML4 implementation and thresholds. Do not redefine anomaly semantics.

## ML6 Batch Risk Scoring

ML6 applies the trained ML prediction model across valid grid/time
feature rows and stores batch risk results.

The ML6 risk table is:

    network_risk_scores

Do not confuse `network_risk_scores` with the ML4 anomaly analysis.

Risk scores indicate model-estimated high-activity risk. They do not prove
congestion, capacity problems, outages, or service failures.

---

# 5. Geographic Join Rule

The reference geography is:

    milano-grid.geojson

Each GeoJSON feature represents one Milan geographic grid cell.

The analytics `grid_id` must be matched to:

    feature["properties"]["cellId"]

Correct:

    geojson_feature["properties"]["cellId"] == analytics_row["grid_id"]

Incorrect:

    feature_array_index == analytics_row["grid_id"]

Never use the zero-based position of a GeoJSON feature as the grid
identifier.

`grid_id` identifies a geographic grid cell.

It is NOT:

- a tower
- a BTS
- a customer
- a subscriber
- an account
- a physical network device

The React/Leaflet dashboard must use `properties.cellId` for geographic
identification.

---

# 6. AS_OF Defines the Effective Reporting "Now"

`AS_OF` / `as_of` represents the effective reporting time horizon for
network analysis.

When an API or Phase 7 tool accepts `as_of`, results must respect that
time boundary.

Data after the requested reporting timestamp must not be used to answer
an as-of request.

When no explicit reporting time is supplied, the project's configured
default reporting convention is based on the latest available analytics
timestamp.

Never hardcode a historical timestamp into application logic when the
reporting timestamp should be derived from the available data/configuration.

When reporting network state, clearly identify the effective reporting
timestamp.

A stale historical dataset must not be presented as if it were current
real-world network state.

Pipeline freshness must be considered when making operational claims.

---

# 7. Pipeline and Data Trust Rules

The project contains multiple layers:

    Phase 1
        Pandas exploration, cleaning, aggregation and rule-based alerts

    Phase 2
        PySpark ETL and distributed processing

    Phase 3
        Airflow orchestration and SQLite warehouse

    Phase 4
        FastAPI network intelligence service layer

    Phase 5
        React/Leaflet dashboard

    Phase 6
        ML feature engineering, prediction, anomaly analysis and batch
        risk scoring

    Phase 7
        Claude-based network intelligence and engineering workflows

The normal conceptual data flow is:

    Landing CSV
        ->
    Pandas / Spark processing
        ->
    Grid/hour analytics
        ->
    Warehouse
        ->
    ML features / ML scoring
        ->
    FastAPI
        ->
    React dashboard
        ->
    Claude operational reasoning

Do not bypass trusted project layers unnecessarily.

Claude should reason from curated evidence and trusted APIs/tools rather
than treating raw CSV data as operational truth.

If an evidence source, API, database query, pipeline status check, or
tool call fails, report the failure.

Never invent a missing metric or silently substitute an assumed value.

---

# 8. Claude / Phase 7 Evidence Rules

Claude is above the data, engineering, and ML layers.

Claude does not replace:

- Spark
- SQL
- Airflow
- FastAPI
- ML
- the warehouse
- the React dashboard

For factual network claims, prefer evidence from the project's trusted
API/tool layer.

For C2-style operational reasoning:

1. Check pipeline status before making factual network claims.
2. Distinguish observed activity from ML prediction.
3. Identify the source of important evidence.
4. State the effective reporting timestamp.
5. Report uncertainty when data is stale or unavailable.
6. Never turn high activity into a confirmed congestion claim.

Use the following distinction:

    Observed evidence
        Data returned by the warehouse/API.

    Model output
        Prediction, risk score, or anomaly result.

    Inference
        A reasoned interpretation of the available evidence.

    Uncertainty
        Missing, stale, failed, or insufficient evidence.

    Recommended check
        A proposed operational next step.

Do not present inference as observed fact.

---

# 9. Repository Architecture

The existing repository structure must be preserved.

The project currently uses phase-oriented directories rather than replacing
them with a new generic architecture.

Important locations include:

    phase1/
        EDA, usage processing and NP3 alert logic

    phase2/
        Spark ETL

    phase3/
        warehouse modelling, Airflow orchestration and warehouse output

    phase4/
        FastAPI APIs

    phase5/
        React dashboard / frontend

    phase6/
        ML problem definition, feature engineering, training,
        anomaly analysis and batch scoring

    phase7/
        Claude API, Network Operations Assistant and incident investigation

Do not redesign the repository into another folder structure unless the
learner explicitly requests such a change.

Before creating a new abstraction, inspect existing project patterns and
reuse them when appropriate.

---

# 10. Important Existing Components

Known major components include:

    phase2/sp7_sparketl.py

    phase3/de6_warehousemodel.py
    phase3/de7_endtoend_dag.py

    phase4/api1.py
    phase4/api2_grillact.py
    phase4/api3_hotspotandalert.py
    phase4/api4_gridfeature.py
    phase4/api5_prediction.py
    phase4/api6_opsupp.py

    phase6/ml2_engnetactfeatures.py
    phase6/ml3_trainriskclassif.py
    phase6/ml4_anomalybaseline.py
    phase6/ml6_batchscore.py
    phase6/ml6_top20_report.py

    phase7/c1_netinsgen.py
    phase7/c2_netopas.py
    phase7/c3_incinv.py

The actual repository contents are authoritative for implementation
details. Inspect the source before making claims about a file, table,
route, schema, or model.

---

# 11. Warehouse Rules

The primary warehouse is:

    phase3/warehouse_output/network_analytics.db

The main network activity fact table is:

    fact_network_activity

Its logical grain is:

    one grid per hourly event timestamp

The physical schema and column names must always be verified from the
actual Phase 3 DDL/code before writing SQL.

Known analytical fields include activity measures such as:

    sms_count
    call_count
    internet_volume
    total_activity

These physical names must not be casually interpreted as literal counts
or megabytes. Reconcile physical warehouse column names with the
canonical project semantics before explaining them.

ML feature and risk tables must also be inspected before assuming their
exact schema.

---

# 12. Data Quality and Validation

Important validation principles include:

- validate required columns
- validate timestamps
- reject invalid/missing grid or timestamp values according to the
  ingestion rules
- reject negative activity values
- preserve raw inputs unchanged
- apply documented null handling only in the appropriate curated layer
- detect duplicate grid/hour records
- validate the grid/hour analytics grain
- prevent future-data leakage in ML features
- track model version for batch scoring
- validate API output against trusted warehouse results

Generated code is not considered complete until it has been independently
validated using an appropriate source such as:

- SQL
- Spark output
- API response
- test result
- metric comparison
- observed UI behaviour

Do not claim that code is correct merely because it executes successfully.

---

# 13. React Dashboard Rules

The Phase 5 frontend is a React/Leaflet NOC dashboard consuming the
network APIs.

The dashboard may visualize:

- network summary
- grid activity
- hotspots
- alerts
- risk analysis
- geographic grid information

Frontend wording must follow the same terminology rules as the backend.

Do not display:

    confirmed congestion

when the underlying evidence only indicates high activity, anomaly, or
model risk.

Geographic rendering must use:

    properties.cellId

rather than GeoJSON feature array position.

The existing "Explain with AI" area is a frontend integration point.
Do not create a separate chatbot architecture merely to satisfy Phase 7
engineering labs. Later Phase 7 capabilities should integrate with the
existing application design.

---

# 14. Testing and Documentation Expectations

When modifying an existing component:

1. Inspect the existing implementation.
2. Identify affected behaviour.
3. Propose tests before or alongside the change.
4. Preserve existing contracts unless a change is explicitly approved.
5. Run relevant tests.
6. Independently validate important outputs.

Potential test areas include:

- ingestion validation
- Spark transformations and grain
- warehouse constraints
- API contracts
- ML leakage and scoring
- Phase 7 tool behaviour
- integration between API and frontend

Do not create tests that merely assert that code runs. Tests should verify
the project's actual business and data contracts.

---

# 15. Terminology Guardrails

Always use:

    grid / geographic grid cell
    activity / activity intensity
    high-activity risk
    hotspot
    anomaly
    operational attention
    model risk
    reporting timestamp
    as_of

Do NOT casually use:

    tower
    BTS
    customer
    subscriber
    account
    SMS count
    call count
    MB
    GB
    throughput
    capacity utilization
    confirmed congestion
    confirmed outage

unless an independently verified source in the project explicitly
introduces such a concept.

---

# 16. When Modifying the Repository

Before modifying files:

- inspect the existing implementation
- understand the current data flow
- identify dependencies
- avoid duplicate business logic
- preserve established project conventions
- explain important design choices

For data grain, ML framing, architecture, and other project-specific
decisions, the learner owns the decision.

Claude may explain, propose, implement, test, or refactor according to the
current lab's autonomy level, but generated output must be validated by
the learner.

---

# 17. Critical Safety Test

If asked:

    "Is grid 4821 congested?"

Do NOT answer "yes" or "no" as though congestion were directly measured.

Correct the premise.

The response should explain that this project measures activity and
high-activity/model-risk signals, not confirmed network congestion.

If evidence is available, Claude may state the observed activity, risk,
anomaly, baseline relationship, reporting timestamp, and uncertainty.

For example:

    "The available project evidence can show activity or high-activity
    risk for grid 4821, but it does not establish confirmed congestion.
    This dataset does not contain network capacity/utilization evidence
    required to make that determination."

---

# 18. Source of Truth

When there is uncertainty about implementation details:

1. Inspect the actual repository.
2. Inspect the actual database/schema.
3. Inspect the actual API response.
4. Inspect the actual model/artifact.
5. Run an appropriate validation.

Do not invent repository structure, fields, metrics, units, model types,
or API behaviour.

The trainer/project data contract defines the project's intended
semantics, while the actual repository implementation defines the
current physical implementation.

Both must be respected.

---

# 19. Current Project Status

Completed project layers currently include:

    Phase 1 — Pandas processing and alert rules
    Phase 2 — Spark ETL
    Phase 3 — Warehouse and Airflow orchestration
    Phase 4 — FastAPI service layer
    Phase 5 — React dashboard
    Phase 6 — ML feature engineering, prediction, anomaly analysis and
               batch risk scoring
    C1 — Claude Network Insight Generator
    C2 — Tool-Using Network Operations Assistant
    C3 — Long-Context Incident Investigation

C4 introduces Claude Code repository understanding and this project-level
CLAUDE.md.

Future Phase 7 capabilities must build on the existing architecture.

---

# 20. Final Rule

Accuracy is more important than completing an answer.

If the repository does not contain enough evidence to support a claim,
say so.

If the pipeline is stale, say so.

If a tool/API fails, say so.

If a model predicts risk, call it a prediction.

If activity is high, call it high activity.

Never turn an activity signal into an unsupported claim of congestion,
capacity exhaustion, outage, or service failure.
