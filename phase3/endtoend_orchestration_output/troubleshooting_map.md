# End-to-End Airflow Orchestration — Troubleshooting Map

| Failure type | Module / task | First place to inspect |
|---|---|---|
| Missing held-back file | ingest | `de7_end_to_end_dag.py` |
| Empty or invalid input | validate | `de7_end_to_end_dag.py` |
| Processing failure | spark_process | `telecom_pipeline.py` |
| Warehouse failure | load_warehouse | `de6_warehouse.py` |
| Missing output or quality failure | quality_check | `de7_end_to_end_dag.py` |
| Notification/status failure | notify | `de7_end_to_end_dag.py` |
