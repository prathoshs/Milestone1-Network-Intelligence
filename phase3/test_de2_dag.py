from datetime import datetime
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
import sys

PROJECT_DIR = "/home/prathosh/Milestone1-Network-Intelligence"
sys.path.insert(0, f"{PROJECT_DIR}/phase3")

import de2_ingestion

def run_de2_ingestion():
    de2_ingestion.main()
with DAG(
    dag_id="de2_ingestion",
    start_date=datetime(2026, 8, 29),
    schedule="@daily",
    catchup=False,
    tags=["phase3", "de2"],
) as dag:

    run_ingestion = PythonOperator(
        task_id="run_de2_ingestion",
        python_callable=run_de2_ingestion,
    )