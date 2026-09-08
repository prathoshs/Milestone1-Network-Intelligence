# DE8 — Failure Handling Matrix

| Fault type | Expected action | Implemented control / evidence |
|---|---|---|
| Missing daily file | FAIL | DE7 ingest/validation failure |
| Duplicate file / duplicate ingestion | CONTINUE | DE2 duplicate detection |
| Malformed timestamp | REJECT | DE2 timestamp validation |
| Negative activity values | REJECT | DE2 minimum quality validation |
| Missing/unexpected column | REJECT | DE2 schema validation |
| Partially corrupt file | REJECT | DE2 row-level validation |
| Spark job failure | FAIL | Spark subprocess failure detection |

## Implemented Controls

1. Duplicate detection / idempotent ingestion
2. Schema validation
3. Timestamp validation
4. Negative activity validation
5. Corrupt-row validation
6. Spark failure detection

## Safe Rerun

Analytics layer was verified after rerun:

- Total rows: 479999
- Unique `(grid_id, event_time)`: 479999
- Duplicate query: no rows returned
