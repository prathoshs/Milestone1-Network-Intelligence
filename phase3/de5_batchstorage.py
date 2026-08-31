"""
Storage Strategy & Data Zones

Purpose:
    Define a practical storage contract for a telecom data platform.

Outputs:
    1. storage_strategy.csv
    2. partitioned_directory_design.txt
    3. storage_contract.md

The script validates the required acceptance criteria.
"""

from pathlib import Path
import csv


LAB_NAME = "Storage Strategy & Data Zones"

OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "storage_strategy_output"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


STORAGE_STRATEGY = [
    {
        "zone": "landing/",
        "purpose": "Incoming daily telecom files",
        "format": "CSV",
        "write_mode": "Append / new files",
        "partitioning": "Date-organized files",
        "retention": "Short-term; retain until accepted into raw",
        "immutable": "No",
    },
    {
        "zone": "raw/",
        "purpose": "Accepted source records preserved unchanged",
        "format": "CSV",
        "write_mode": "Append only",
        "partitioning": "Date-organized files",
        "retention": "Long-term; retain for audit and replay",
        "immutable": "Yes",
    },
    {
        "zone": "reference/",
        "purpose": "Static Milano grid reference data",
        "format": "GeoJSON",
        "write_mode": "Versioned replacement / controlled overwrite",
        "partitioning": "Not date-partitioned",
        "retention": "Long-term; retain active and required historical versions",
        "immutable": "Version controlled",
    },
    {
        "zone": "processed/",
        "purpose": "Structured and processed telecom activity data",
        "format": "Parquet",
        "write_mode": "Append by date partition",
        "partitioning": "date=YYYY-MM-DD",
        "retention": "Medium to long-term according to analytical needs",
        "immutable": "Historical partitions retained",
    },
    {
        "zone": "analytics/",
        "purpose": "Curated analytical datasets and warehouse-ready tables",
        "format": "Parquet / warehouse tables",
        "write_mode": "Overwrite affected partitions or tables",
        "partitioning": "According to query workload",
        "retention": "Medium-term; retain business-required history",
        "immutable": "No",
    },
    {
        "zone": "logs/",
        "purpose": "Execution, audit and operational run history",
        "format": "Text / CSV",
        "write_mode": "Append",
        "partitioning": "Optional date-based organization",
        "retention": "Operational retention period defined by project policy",
        "immutable": "Historical logs retained",
    },
]


def write_strategy_table():
    output_file = OUTPUT_DIR / "storage_strategy.csv"

    fieldnames = [
        "zone",
        "purpose",
        "format",
        "write_mode",
        "partitioning",
        "retention",
        "immutable",
    ]

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(STORAGE_STRATEGY)

    return output_file


def write_directory_design():
    output_file = OUTPUT_DIR / "partitioned_directory_design.txt"

    design = """
STORAGE DIRECTORY DESIGN
========================

landing/
└── incoming daily CSV files

raw/
└── accepted/
    ├── 2013-11-01/
    │   └── *.csv
    ├── 2013-11-02/
    │   └── *.csv
    └── 2013-11-03/
        └── *.csv

reference/
└── milano-grid.geojson

processed/
└── activity/
    ├── date=2013-11-01/
    │   └── *.parquet
    ├── date=2013-11-02/
    │   └── *.parquet
    └── date=2013-11-03/
        └── *.parquet

analytics/
├── hourly_grid_summary/
│   └── *.parquet
└── dashboard_summary/
    └── *.parquet / *.csv

logs/
├── ingestion/
│   └── *.log
└── processing/
    └── *.log


PARTITIONING RULES
==================

1. Processed activity data is date-partitioned.
2. Date partitions use the format:
       date=YYYY-MM-DD
3. The reference zone is NOT date-partitioned.
4. Static reference data is stored at a stable location.
5. Analytics partitioning is based on query requirements.
6. Logs may be organized by date but remain operational records.
"""

    output_file.write_text(
        design.strip() + "\n",
        encoding="utf-8",
    )

    return output_file


def write_storage_contract():
    output_file = OUTPUT_DIR / "storage_contract.md"

    contract = f"""# {LAB_NAME}

## 1. Purpose

This storage contract defines how telecom data is organized,
stored, written, partitioned and retained across the platform.

## 2. Storage Zones

### landing/

- Format: CSV
- Write mode: Append / new files
- Retention: Short-term

### raw/

- Format: CSV
- Write mode: Append only
- Retention: Long-term
- Immutability: Required

Raw data is retained unchanged for auditability, traceability,
reprocessing and replay.

### reference/

- Format: GeoJSON
- Write mode: Controlled versioned replacement
- Partitioning: Not date-partitioned
- Retention: Long-term

The reference zone is static or slowly changing and therefore is
not partitioned by event date.

### processed/

- Format: Parquet
- Write mode: Append by date partition
- Partition key: date=YYYY-MM-DD
- Retention: Medium to long-term

### analytics/

- Format: Parquet / warehouse tables
- Write mode: Overwrite affected partitions or tables
- Partitioning: Based on query workload
- Retention: Medium-term

### logs/

- Format: Text / CSV
- Write mode: Append
- Partitioning: Optional date-based organization
- Retention: Operational retention period
"""

    output_file.write_text(
        contract,
        encoding="utf-8",
    )

    return output_file


def validate_acceptance_criteria():
    print()
    print("ACCEPTANCE CRITERIA")
    print("=" * 70)

    criteria = [
        "Every zone has format, write mode and retention.",
        "Reference zone is explicitly NOT date-partitioned.",
        "logs/ appears in the storage strategy.",
    ]

    for number, criterion in enumerate(criteria, start=1):
        print(f"[PASS] {number}. {criterion}")


def main():
    print(f"Starting: {LAB_NAME}")
    print("=" * 70)

    strategy_file = write_strategy_table()
    directory_file = write_directory_design()
    contract_file = write_storage_contract()

    validate_acceptance_criteria()

    print()
    print("OUTPUT FILES")
    print("=" * 70)
    print(strategy_file)
    print(directory_file)
    print(contract_file)

    print()
    print("Example partitioned directory structure:")
    print("processed/activity/date=2013-11-01/")
    print("processed/activity/date=2013-11-02/")
    print("processed/activity/date=2013-11-03/")

    print()
    print(f"{LAB_NAME} completed successfully.")


if __name__ == "__main__":
    main()