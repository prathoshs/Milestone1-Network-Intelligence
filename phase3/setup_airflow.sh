#!/bin/bash
set -e

echo "=== Airflow setup started ==="

sudo apt update
sudo apt install -y curl

echo "=== Installing uv ==="
curl -LsSf https://astral.sh/uv/install.sh | sh

export PATH="$HOME/.local/bin:$PATH"

echo "=== Installing Python 3.11 ==="
uv python install 3.11

echo "=== Creating Airflow environment ==="
cd /mnt/c/Users/Admin/Milestone1-Network-Intelligence

uv venv --python 3.11 airflow_venv

source airflow_venv/bin/activate

echo "=== Upgrading pip ==="
uv pip install --upgrade pip

echo "=== Installing Airflow ==="
AIRFLOW_VERSION=3.1.0
PYTHON_VERSION=3.11

uv pip install "apache-airflow==${AIRFLOW_VERSION}" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

echo "=== Checking Airflow ==="
airflow version

echo "=== Airflow installation completed ==="
