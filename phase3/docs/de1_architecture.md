# DE1 — Telecom Data Architecture

## 1. Architecture Diagram

```text
                    ┌──────────────────────────────┐
                    │ Daily Activity CSV Files     │
                    │ sms-call-internet-mi-*.csv  │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ LANDING                      │
                    │ Incoming files               │
                    └──────────────┬───────────────┘
                                   │
                              Validate
                                   │
                    ┌──────────────┴───────────────┐
                    │                              │
                 INVALID                         VALID
                    │                              │
                    ▼                              ▼
             ┌─────────────┐              ┌─────────────┐
             │  REJECTED   │              │     RAW     │
             │ Failed files│              │ Accepted CSV│
             └─────────────┘              └──────┬──────┘
                                                 │
                                                 ▼
                                      ┌────────────────────┐
                                      │       SPARK        │
                                      │ Transform activity │
                                      └─────────┬──────────┘
                                                │
                                                ▼
                                      ┌────────────────────┐
                                      │    PROCESSED       │
                                      │ Curated Parquet    │
                                      └─────────┬──────────┘
                                                │
                                                ▼
                                      ┌────────────────────┐
                                      │     ANALYTICS      │
                                      │ Aggregations +     │
                                      │ intelligence       │
                                      └─────────┬──────────┘
                                                │
                                                ▼
                                      ┌────────────────────┐
                                      │ SQL / WAREHOUSE    │
                                      │ Queryable tables   │
                                      └─────────┬──────────┘
                                                │
                         ┌──────────────────────┼─────────────────────┐
                         │                      │                     │
                         ▼                      ▼                     ▼
                   ┌──────────┐           ┌──────────┐         ┌──────────┐
                   │ FastAPI  │           │   React  │         │    ML    │
                   │ Serving  │           │Dashboard │         │ Scoring  │
                   └────┬─────┘           └──────────┘         └────┬─────┘
                        │                                            │
                        └──────────────────┬─────────────────────────┘
                                           ▼
                                     ┌────────────┐
                                     │  Claude    │
                                     │ Reasoning  │
                                     └────────────┘


STATIC REFERENCE PATH
──────────────────────────────────────────────────────────────────────
┌──────────────────────────────┐
│ milano-grid.geojson          │
│ Static reference data        │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ REFERENCE                    │
│ GeoJSON                      │
└──────────────┬───────────────┘
               │
               ▼
        ┌─────────────┐
        │    SPARK    │
        │ Enrichment  │
        └─────────────┘

Reference data does NOT pass through the daily Landing → Raw flow.
```

## 2. Layer, Format and Tool Mapping

| Layer     | Data                                | Format               | Primary Tool   |
| --------- | ----------------------------------- | -------------------- | -------------- |
| Landing   | Incoming daily activity files       | CSV                  | Python         |
| Raw       | Validated source files              | CSV                  | Python         |
| Rejected  | Invalid source files                | CSV / original file  | Python         |
| Reference | Milan grid geometry                 | GeoJSON              | Python / Spark |
| Processed | Cleaned and transformed activity    | Parquet              | Spark          |
| Analytics | Network intelligence datasets       | Parquet / SQL tables | Spark + SQL    |
| Warehouse | Queryable fact and dimension tables | SQL tables           | SQL            |
| Serving   | Curated API responses               | JSON                 | FastAPI        |

## 3. Analytics Outputs

The analytics layer will provide:
* `hourly_grid_summary` — network activity at `grid_id + timestamp` grain.
* `daily_grid_summary` — daily activity summarized by grid.
* `hotspots` — grids and periods exhibiting significant network activity or concentration.
* `alert` tables — operational investigation signals derived from network activity.
* `risk` tables — risk/scoring outputs produced from the curated network evidence.

The existing Phase 2 `hourly_grid_summary` remains the established hourly activity dataset and uses the existing `grid_id + timestamp` grain.

## 4. Tool Responsibility Mapping

| Component   | Exactly One Responsibility                                                       |
| ----------- | -------------------------------------------------------------------------------- |
| **Spark**   | Performs distributed data transformation, aggregation and geospatial enrichment. |
| **SQL**     | Stores and queries curated analytics and warehouse tables.                       |
| **Airflow** | Orchestrates pipeline tasks and their dependencies.                              |
| **FastAPI** | Serves curated network intelligence through API endpoints.                       |
| **React**   | Presents network intelligence through the dashboard interface.                   |
| **ML**      | Produces predictive/anomaly risk scores from curated features.                   |
| **Claude**  | Reasons over curated evidence and explains network intelligence findings.        |

## 5. Quality Gates

### Gate 1 — Before Raw Acceptance

A file may move from `landing` to `raw` only when:

* Required columns are present.
* Column names match the data contract.
* Timestamp values are valid.
* Expected data types are valid.
* Activity measures are valid.
* Negative activity values are rejected.
* The file is not a duplicate ingestion.
* The file can be read successfully.
* An ingestion/audit record is created.

Invalid files are routed to `rejected` with a specific rejection reason.

### Gate 2 — Before Analytics Publication
Analytics may be published only when:

* Spark processing completes successfully.
* Expected rows are produced.
* The expected `grid_id + timestamp` grain is maintained.
* Duplicate grid-hours are absent.
* Required grid enrichment succeeds.
* Required analytics columns are present.
* No unintended geometry is included in hourly analytics.
* Warehouse loading succeeds.
* Final quality checks pass.
* Pipeline health/status is recorded.

## 6. Pipeline Health

Pipeline health will be recorded in a **machine-readable pipeline status/audit location** containing run-level and task-level execution information.
The health record will provide the operational status that the later **API6** endpoint can expose.
At minimum, it will identify:

* `run_id`
* run timestamp
* task status
* rows in
* rows rejected
* rows published
* relevant quality-check results
* `AS_OF`

## 7. Assumptions

1. Daily network activity arrives as CSV files.
2. The daily files represent batch data rather than a continuous streaming source.
3. `milano-grid.geojson` is static reference data and is not ingested as a daily activity file.
4. `grid_id` identifies the geographic grid cell.
5. The established Phase 2 hourly grain remains `grid_id + timestamp`.
6. Spark remains the transformation engine.
7. SQL is used for curated analytical storage and querying.
8. Airflow controls orchestration rather than performing business transformations.
9. FastAPI serves curated outputs rather than raw files.
10. ML produces scores; it does not replace deterministic Spark/SQL transformations.
11. Claude consumes curated evidence rather than directly processing the raw dataset.

## 8. Non-Goals

This project does **not** attempt to provide:

* Telecom capacity measurement.
* Network throughput measurement.
* Network utilization measurement.
* Packet-level network performance.
* Tower/BTS-level engineering telemetry.
* Customer-level behavioural profiling.
* Real-time streaming implementation in this phase.
* Automated operational actions based solely on model output.

**Explicit data limitation:** we do not have capacity, throughput or utilization data.

## DE1 Acceptance Checklist

☑ Every component has exactly one stated responsibility.
☑ No responsibility is duplicated between Spark, SQL, Airflow, FastAPI, React, ML and Claude.
☑ `milano-grid.geojson` is represented as a separate static reference path.
☑ The reference data does not pass through the daily Landing → Raw ingestion flow.
☑ Analytics outputs include `hourly_grid_summary`, `daily_grid_summary`, `hotspots`, alert tables and risk tables.
☑ Quality gates are defined before Raw acceptance and Analytics publication.
☑ A non-goals list exists.
☑ The non-goals explicitly state: **“we do not have capacity, throughput or utilization data”.**
☑ Pipeline health is explicitly recorded in a machine-readable status/audit location for later API6 exposure.

**DE1 STATUS: COMPLETE**
