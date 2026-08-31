# from datetime import datetime
# import os
# import subprocess

# # from airflow import DAG
# # from airflow.operators.python import PythonOperator


# # ============================================================
# # CONFIGURATION
# # ============================================================

# PROJECT_DIR = "/mnt/c/Users/Admin/Milestone1-Network-Intelligence"

# AIRFLOW_PYTHON = os.path.expanduser(
#     "~/airflow_venv/bin/python"
# )

# DE2_SCRIPT = os.path.join(
#     PROJECT_DIR,
#     "phase3",
#     "de2_ingestion.py",
# )

# SPARK_SCRIPT = os.path.join(
#     PROJECT_DIR,
#     "phase3",
#     "telecom_pipeline.py",
# )

# RAW_PATH = os.path.join(
#     PROJECT_DIR,
#     "phase3",
#     "data",
#     "raw",
# )

# PROCESSED_PATH = os.path.expanduser("~/de3_output/processed")

# ANALYTICS_PATH = os.path.expanduser("~/de3_output/analytics")

# REFERENCE_PATH = os.path.join(
#     PROJECT_DIR,
#     "phase3",
#     "data",
#     "reference",
#     "milano-grid.geojson",
# )

# LOG_DIR = os.path.join(
#     PROJECT_DIR,
#     "phase3",
#     "logs",
# )

# SPARK_LOG = os.path.join(
#     LOG_DIR,
#     "spark_job_log.txt",
# )


# # ============================================================
# # DE2 INGESTION
# # ============================================================

# def run_de2_ingestion():
#     subprocess.run(
#         [
#             AIRFLOW_PYTHON,
#             DE2_SCRIPT,
#         ],
#         check=True,
#     )


# # ============================================================
# # SPARK PROCESSING
# # ============================================================

# def run_spark_job():
#     os.makedirs(LOG_DIR, exist_ok=True)

#     start = datetime.now().isoformat()

#     command = [
#         AIRFLOW_PYTHON,
#         SPARK_SCRIPT,
#         "--input",
#         RAW_PATH,
#         "--processed",
#         PROCESSED_PATH,
#         "--analytics",
#         ANALYTICS_PATH,
#         "--reference",
#         REFERENCE_PATH,
#     ]

#     with open(SPARK_LOG, "a") as log:

#         log.write("\n")
#         log.write("=" * 60 + "\n")
#         log.write(f"START_TIME={start}\n")
#         log.write("STATUS=STARTED\n")

#         try:
#             subprocess.run(
#                 command,
#                 stdout=log,
#                 stderr=log,
#                 text=True,
#                 check=True,
#             )

#             end = datetime.now().isoformat()

#             log.write(f"END_TIME={end}\n")
#             log.write("STATUS=SUCCESS\n")

#         except subprocess.CalledProcessError as exc:

#             end = datetime.now().isoformat()

#             log.write(f"END_TIME={end}\n")
#             log.write("STATUS=FAILED\n")
#             log.write(
#                 f"RETURN_CODE={exc.returncode}\n"
#             )

#             raise


# # ============================================================
# # AIRFLOW DAG
# # ============================================================

# with DAG(
#     dag_id="de3_spark_pipeline",
#     start_date=datetime(2026, 8, 29),
#     schedule=None,
#     catchup=False,
#     tags=[
#         "phase3",
#         "de3",
#         "spark",
#     ],
# ) as dag:

#     ingestion = PythonOperator(
#         task_id="de2_ingestion",
#         python_callable=run_de2_ingestion,
#     )

#     spark_processing = PythonOperator(
#         task_id="spark_processing",
#         python_callable=run_spark_job,
#     )

#     ingestion >> spark_processing