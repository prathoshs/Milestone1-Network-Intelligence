"""
End-to-End Airflow Orchestration

Purpose:
    Orchestrate the complete telecom batch flow from one trigger.

Flow:
    ingest
        ↓
    validate
        ↓
    spark_process
        ↓
    load_warehouse
        ↓
    quality_check
        ↓
    notify

The DAG contains orchestration only.
Processing logic remains in the existing modules.
"""
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import logging
import subprocess
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
# ============================================================
# PROJECT CONFIGURATION
# ============================================================
PROJECT_DIR = Path.home() / "Milestone1-Network-Intelligence"
PHASE3_DIR = PROJECT_DIR / "phase3"
AIRFLOW_PYTHON = Path.home() / "airflow_venv" / "bin" / "python"
OUTPUT_DIR = PHASE3_DIR / "endtoend_orchestration_output"
STATUS_FILE = OUTPUT_DIR / "pipeline_status.json"
RUN_LOG = OUTPUT_DIR / "pipeline_run.log"
TROUBLESHOOTING_FILE = OUTPUT_DIR / "troubleshooting_map.md"
RAW_DIR = PHASE3_DIR / "data" / "raw"
PROCESSED_DIR = PHASE3_DIR / "data" / "processed"
ANALYTICS_DIR = PHASE3_DIR / "data" / "analytics"
WAREHOUSE_DIR = PHASE3_DIR / "warehouse_output"
HELD_BACK_FILE = (
    PHASE3_DIR
    / "data"
    / "landing"
    / "sms-call-internet-mi-2013-11-07.csv"
)
# ============================================================
# LOGGING
# ============================================================
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=RUN_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
def pipeline_failure_callback(context):
    task_instance = context.get("task_instance")
    exception = context.get("exception")

    record = {
        "pipeline": "End-to-End Airflow Orchestration",
        "status": "FAILED",
        "as_of": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "quality_check": "FAIL",
        "failed_task": task_instance.task_id if task_instance else "unknown",
        "error": str(exception) if exception else "unknown",
    }

    run_id = (
        task_instance.run_id
        if task_instance
        else "unknown"
    )
    failure_status_file = (
        OUTPUT_DIR / f"pipeline_status_failed_{run_id}.json"
    )
    failure_status_file.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )
    STATUS_FILE.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )

    logging.error(
        "PIPELINE_STATUS=FAILED | task=%s | error=%s",
        record["failed_task"],
        record["error"],
    )
# ============================================================
# HELPER
# ============================================================
def run_command(command):
    logging.info("RUNNING: %s", " ".join(map(str, command)))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logging.info(result.stdout)
    if result.stderr:
        logging.info(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with return code {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
# ============================================================
# TASK 1 — INGEST
# ============================================================
def ingest():
    logging.info("Starting ingest")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not HELD_BACK_FILE.exists():
        raise FileNotFoundError(
            f"Held-back file not found: {HELD_BACK_FILE}"
        )
    target = RAW_DIR / HELD_BACK_FILE.name
    if target.exists():
        logging.info("File already present in raw: %s", target)
        return
    target.write_bytes(
        HELD_BACK_FILE.read_bytes()
    )
    logging.info(
        "Ingested file: %s",
        target,
    )
# ============================================================
# TASK 2 — VALIDATE
# ============================================================
def validate():
    logging.info("Starting validation")
    csv_files = list(RAW_DIR.glob("*.csv"))
    if not csv_files:
        raise RuntimeError(
            "Validation failed: raw directory contains no CSV files"
        )
    for file in csv_files:
        if file.stat().st_size == 0:
            raise RuntimeError(
                f"Validation failed: empty file {file.name}"
            )
    logging.info(
        "Validation passed for %d CSV files",
        len(csv_files),
    )
# ============================================================
# TASK 3 — SPARK PROCESS
# ============================================================
def spark_process():
    logging.info("Starting Spark processing")
    script = PHASE3_DIR / "telecom_pipeline.py"
    if not script.exists():
        raise FileNotFoundError(
            f"Processing module not found: {script}"
        )
    run_command(
        [
            str(AIRFLOW_PYTHON),
            str(script),
            "--input",
            str(RAW_DIR),
            "--processed",
            str(PROCESSED_DIR),
            "--analytics",
            str(ANALYTICS_DIR),
            "--reference",
            str(
                PHASE3_DIR
                / "data"
                / "reference"
                / "milano-grid.geojson"
            ),
        ]
    )
    logging.info("Spark processing completed")
# ============================================================
# TASK 4 — LOAD WAREHOUSE
# ============================================================
def load_warehouse():
    logging.info("Starting warehouse load")
    warehouse_script = (
        PHASE3_DIR / "de6_warehousemodel.py"
    )
    if not warehouse_script.exists():
        raise FileNotFoundError(
            f"Warehouse module not found: {warehouse_script}"
        )
    run_command(
        [
            str(AIRFLOW_PYTHON),
            str(warehouse_script),
        ]
    )
    logging.info("Warehouse load completed")
# ============================================================
# TASK 5 — QUALITY CHECK
# ============================================================
def get_latest_analytics_timestamp():
    db_path =WAREHOUSE_DIR / "network_analytics.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT MAX(event_time)
            FROM fact_network_activity
            """
        ).fetchone()
        if row is None or row[0] is None:
            raise RuntimeError(
                "Analytics warehouse contains no event_time"
            )
        return row[0]
    finally:
        conn.close()
def quality_check():
    logging.info("Starting quality check")
    processed_activity = PROCESSED_DIR / "activity"
    hourly_summary = ANALYTICS_DIR / "hourly_grid_summary"
    dashboard_summary = ANALYTICS_DIR / "dashboard_summary"
    checks = {
        "processed_activity_exists": processed_activity.exists(),
        "hourly_summary_exists": hourly_summary.exists(),
        "dashboard_summary_exists": dashboard_summary.exists(),
        "warehouse_exists": WAREHOUSE_DIR.exists(),
    }
    status = "SUCCESS" if all(checks.values()) else "FAILED"
    # --------------------------------------------------------
    # Analytics AS_OF from warehouse
    # --------------------------------------------------------
    as_of = get_latest_analytics_timestamp()
    # --------------------------------------------------------
    # Operational row counts
    # --------------------------------------------------------
    rows_in = len(list(RAW_DIR.glob("*.csv")))
    rows_rejected = 0
    rejected_dir = PHASE3_DIR / "data" / "rejected"
    if rejected_dir.exists():
        rows_rejected = sum(
            1 for f in rejected_dir.glob("*.csv")
            if f.is_file()
        )
    rows_published = 0
    db_path = WAREHOUSE_DIR / "network_analytics.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM fact_network_activity"
            ).fetchone()
            rows_published = int(row[0]) if row else 0
        finally:
            conn.close()
    # --------------------------------------------------------
    # Nulls handled
    # --------------------------------------------------------
    nulls_handled = 0
    # --------------------------------------------------------
    # Run identifier
    # --------------------------------------------------------
    run_id = datetime.now().strftime(
        "manual__%Y-%m-%dT%H:%M:%S"
    )
    # --------------------------------------------------------
    # Final status record
    # --------------------------------------------------------
    record = {
        "pipeline": "End-to-End Airflow Orchestration",
        "status": status,
        "healthy": status == "SUCCESS",
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "as_of": as_of,
        "quality_check": (
            "PASS"
            if status == "SUCCESS"
            else "FAIL"
        ),
        "rows_in": rows_in,
        "rows_rejected": rows_rejected,
        "nulls_handled": nulls_handled,
        "rows_published": rows_published,
        "checks": checks,
        "reasons": (
            []
            if status == "SUCCESS"
            else [
                name
                for name, passed in checks.items()
                if not passed
            ]
        ),
    }
    STATUS_FILE.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )
    logging.info(
        "Pipeline status written to %s",
        STATUS_FILE,
    )
    if status != "SUCCESS":
        raise RuntimeError("Quality check failed")
# ============================================================
# TASK 6 — NOTIFY
# ============================================================
def notify():
    logging.info("Starting notification")
    if not STATUS_FILE.exists():
        raise RuntimeError(
            "Pipeline status record does not exist"
        )
    record = json.loads(
        STATUS_FILE.read_text(
            encoding="utf-8"
        )
    )
    logging.info(
        "PIPELINE_STATUS=%s",
        record["status"],
    )
    logging.info(
        "AS_OF=%s",
        record["as_of"],
    )
    print(
        f"Pipeline status: {record['status']}"
    )
    print(
        f"AS_OF: {record['as_of']}"
    )
# ============================================================
# TROUBLESHOOTING MAP
# ============================================================
def create_troubleshooting_map():
    content = """# End-to-End Airflow Orchestration — Troubleshooting Map

| Failure type | Module / task | First place to inspect |
|---|---|---|
| Missing held-back file | ingest | `de7_end_to_end_dag.py` |
| Empty or invalid input | validate | `de7_end_to_end_dag.py` |
| Processing failure | spark_process | `telecom_pipeline.py` |
| Warehouse failure | load_warehouse | `de6_warehouse.py` |
| Missing output or quality failure | quality_check | `de7_end_to_end_dag.py` |
| Notification/status failure | notify | `de7_end_to_end_dag.py` |
"""
    TROUBLESHOOTING_FILE.write_text(
        content,
        encoding="utf-8",
    )
create_troubleshooting_map()
# ============================================================
# DAG
# ============================================================
with DAG(
    dag_id="end_to_end_airflow_orchestration",
    on_failure_callback=pipeline_failure_callback,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    description=(
        "End-to-end telecom batch orchestration"
    ),
    tags=[
        "network",
        "analytics",
        "orchestration",
    ],
) as dag:
    ingest_task = PythonOperator(
        task_id="ingest",
        python_callable=ingest,
    )
    validate_task = PythonOperator(
        task_id="validate",
        python_callable=validate,
    )
    spark_task = PythonOperator(
        task_id="spark_process",
        python_callable=spark_process,
    )
    warehouse_task = PythonOperator(
        task_id="load_warehouse",
        python_callable=load_warehouse,
    )
    quality_task = PythonOperator(
        task_id="quality_check",
        python_callable=quality_check,
    )
    notify_task = PythonOperator(
        task_id="notify",
        python_callable=notify,
        trigger_rule="all_success",
    )
    (
        ingest_task
        >> validate_task
        >> spark_task
        >> warehouse_task
        >> quality_task
        >> notify_task
    )