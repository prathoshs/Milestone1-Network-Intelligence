from pathlib import Path
from datetime import datetime
import csv
import shutil
import sys
# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
LANDING_DIR = BASE_DIR / "data" / "landing"
RAW_DIR = BASE_DIR / "data" / "raw"
REJECTED_DIR = BASE_DIR / "data" / "rejected"
REFERENCE_DIR = BASE_DIR / "data" / "reference"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "ingestion_log.csv"
# ============================================================
# RAW DATA CONTRACT
# ============================================================
REQUIRED_COLUMNS = [
    "datetime",
    "CellID",
    "countrycode",
    "smsin",
    "smsout",
    "callin",
    "callout",
    "internet",
]
ACTIVITY_COLUMNS = [
    "smsin",
    "smsout",
    "callin",
    "callout",
    "internet",
]
FILE_PATTERN = "sms-call-internet-mi-*.csv"
# ============================================================
# DIRECTORY SETUP
# ============================================================
def setup_directories():
    LANDING_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
# ============================================================
# 1. DETECT FILES
# ============================================================
def detect_files():
    """
    Detect only Milan daily activity CSV files.

    GeoJSON is not included because the detection pattern
    requires sms-call-internet-mi-*.csv.
    """
    setup_directories()
    files = sorted(LANDING_DIR.glob(FILE_PATTERN))
    return [
        file for file in files
        if file.is_file()
    ]
# ============================================================
# 2. SCHEMA VALIDATION
# ============================================================
def validate_schema(file_path):
    """
    Validate the delivered raw CSV schema.
    """
    try:
        with file_path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            reader = csv.reader(file)
            header = next(reader, None)
            if header is None:
                return False, 0, "EMPTY_FILE"
            header = [column.strip() for column in header]
            missing = [
                column
                for column in REQUIRED_COLUMNS
                if column not in header
            ]
            if missing:
                return (
                    False,
                    0,
                    "MISSING_COLUMNS:"
                    + ",".join(missing)
                )
            return True, 0, "SCHEMA_VALID"
    except Exception as exc:
        return False, 0, f"SCHEMA_READ_ERROR:{exc}"
# ============================================================
# 3. MINIMUM QUALITY VALIDATION
# ============================================================
def validate_minimum_quality(file_path):
    """
    Validate:
    - timestamp
    - CellID
    - activity values
    - row count
    """
    row_count = 0
    try:
        with file_path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                return False, 0, "EMPTY_FILE"
            for line_number, row in enumerate(reader, start=2):
                row_count += 1
                # -------------------------
                # Timestamp
                # -------------------------
                timestamp = row.get("datetime", "").strip()
                if not timestamp:
                    return (
                        False,
                        row_count,
                        f"MISSING_TIMESTAMP_AT_ROW_{line_number}"
                    )
                try:
                    datetime.fromisoformat(
                        timestamp.replace("Z", "+00:00")
                    )
                except ValueError:
                    return (
                        False,
                        row_count,
                        f"MALFORMED_TIMESTAMP_AT_ROW_{line_number}"
                    )
                # -------------------------
                # Grid ID
                # -------------------------
                grid_id = row.get("CellID", "").strip()
                try:
                    grid_id_value = int(grid_id)
                except ValueError:
                    return (
                        False,
                        row_count,
                        f"INVALID_CELLID_AT_ROW_{line_number}"
                    )
                if not 1 <= grid_id_value <= 10000:
                    return (
                        False,
                        row_count,
                        f"CELLID_OUT_OF_RANGE_AT_ROW_{line_number}"
                    )
                # -------------------------
                # Activity values
                # -------------------------
                for column in ACTIVITY_COLUMNS:
                    value = row.get(column, "").strip()
                    # Blank activity fields are allowed.
                    if value == "":
                        continue
                    try:
                        numeric_value = float(value)
                    except ValueError:
                        return (
                            False,
                            row_count,
                            f"NON_NUMERIC_{column}_AT_ROW_{line_number}"
                        )
                    if numeric_value < 0:
                        return (
                            False,
                            row_count,
                            f"NEGATIVE_{column}_AT_ROW_{line_number}"
                        )
            if row_count == 0:
                return False, 0, "NO_DATA_ROWS"
            return True, row_count, "QUALITY_VALID"
    except Exception as exc:
        return False, row_count, f"QUALITY_READ_ERROR:{exc}"
# ============================================================
# AUDIT LOG
# ============================================================
def write_log(filename, status, row_count, reason):
    """
    Write one audit record for every file seen.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = LOG_FILE.exists()
    with LOG_FILE.open(
        "a",
        encoding="utf-8",
        newline=""
    ) as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow([
                "filename",
                "status",
                "row_count",
                "reason",
                "processed_at",
            ])
        writer.writerow([
            filename,
            status,
            row_count,
            reason,
            datetime.now().isoformat(timespec="seconds"),
        ])
# ============================================================
# 4. ROUTE FILE
# ============================================================
def route_file(file_path, valid, row_count, reason):
    """
    Route valid files to raw and invalid files to rejected.
    
    Re-running an already processed filename does not silently
    duplicate it. The file is logged as DUPLICATE.
    """
    if valid:
        destination = RAW_DIR / file_path.name
        if destination.exists():
            write_log(
                file_path.name,
                "DUPLICATE",
                row_count,
                "FILE_ALREADY_EXISTS_IN_RAW"
            )
            return "DUPLICATE"
        shutil.move(
            str(file_path),
            str(destination)
        )
        write_log(
            file_path.name,
            "ACCEPTED",
            row_count,
            reason
        )
        return "ACCEPTED"
    else:
        destination = REJECTED_DIR / file_path.name
        if destination.exists():
            destination.unlink()
        shutil.move(
            str(file_path),
            str(destination)
        )
        write_log(
            file_path.name,
            "REJECTED",
            row_count,
            reason
        )
        return "REJECTED"
# ============================================================
# PROCESS ONE FILE
# ============================================================
def process_file(file_path):
    """
    Validate and route one detected file.
    """
    valid_schema, _, schema_reason = validate_schema(file_path)
    if not valid_schema:
        return route_file(
            file_path,
            False,
            0,
            schema_reason
        )
    valid_quality, row_count, quality_reason = (
        validate_minimum_quality(file_path)
    )
    return route_file(
        file_path,
        valid_quality,
        row_count,
        quality_reason
    )
# ============================================================
# MAIN
# ============================================================
def main():
    setup_directories()
    files = detect_files()
    if not files:
        print("NO_DAILY_FILES_FOUND")
        return 0
    print(f"DETECTED_FILES={len(files)}")
    accepted = 0
    rejected = 0
    duplicate = 0
    for file_path in files:
        print(f"PROCESSING={file_path.name}")
        status = process_file(file_path)
        print(
            f"RESULT={file_path.name} | STATUS={status}"
        )
        if status == "ACCEPTED":
            accepted += 1
        elif status == "REJECTED":
            rejected += 1
        elif status == "DUPLICATE":
            duplicate += 1
    print()
    print("INGESTION SUMMARY")
    print(f"ACCEPTED={accepted}")
    print(f"REJECTED={rejected}")
    print(f"DUPLICATE={duplicate}")
    print(f"LOG={LOG_FILE}")
    return 0

if __name__ == "__main__":
    sys.exit(main())