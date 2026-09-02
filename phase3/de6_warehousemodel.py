"""
Warehouse Modelling for Network Analytics

Purpose:
    Build an analytics-ready relational star schema from
    hourly network activity summaries.

Creates:
    - fact_network_activity
    - dim_time
    - dim_grid

Database:
    SQLite

Validation:
    - fact row count matches source row count
    - dim_grid count matches distinct source grid count
    - no duplicate grid keys
    - fact table contains no geometry column
    - SQL aggregates match source aggregates
    - required indexes exist
"""
from pathlib import Path
import json
import sqlite3
import csv
import sys
try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required.")
    print("Install with: python -m pip install pandas pyarrow")
    sys.exit(1)
LAB_NAME = "Warehouse Modelling for Network Analytics"
PROJECT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = (
    PROJECT_DIR
    / "data"
    / "analytics"
    / "hourly_grid_summary"
)
REFERENCE_FILE = (
    PROJECT_DIR
    / "data"
    / "reference"
    / "milano-grid.geojson"
)
OUTPUT_DIR = (
    PROJECT_DIR
    / "warehouse_output"
)
DATABASE_FILE = OUTPUT_DIR / "network_analytics.db"
VALIDATION_FILE = OUTPUT_DIR / "warehouse_validation.txt"
SQL_FILE = OUTPUT_DIR / "sample_queries.sql"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# ============================================================
# SOURCE DISCOVERY
# ============================================================
def load_source():
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Source directory not found:\n{SOURCE_DIR}"
        )
    files = list(SOURCE_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"No Parquet files found in:\n{SOURCE_DIR}"
        )
    print(f"Source files found: {len(files)}")
    frames = []
    for file in files:
        frames.append(pd.read_parquet(file))
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        raise ValueError("Source dataset is empty.")
    print(f"Source rows: {len(df):,}")
    print(f"Source columns: {list(df.columns)}")
    return df
# ============================================================
# COLUMN DETECTION
# ============================================================
def find_column(df, candidates, required=True):
    lower_map = {
        str(column).lower(): column
        for column in df.columns
    }
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    if required:
        raise ValueError(
            f"Required column not found. Tried: {candidates}"
        )
    return None
def detect_columns(df):
    grid_col = find_column(
        df,
        ["grid_id", "gridid", "grid"]
    )
    time_col = find_column(
        df,
        [
            "datetime",
            "timestamp",
            "hour",
            "time",
            "date_hour",
            "start_time"
        ]
    )
    sms_col = find_column(
        df,
        ["sms", "sms_total", "sms_activity"],
        required=False
    )
    call_col = find_column(
        df,
        ["calls", "call", "call_total", "calls_total"],
        required=False
    )
    internet_col = find_column(
        df,
        [
            "internet",
            "internet_traffic",
            "internet_total",
            "internet_activity"
        ],
        required=False
    )
    return {
        "grid": grid_col,
        "time": time_col,
        "sms": sms_col,
        "calls": call_col,
        "internet": internet_col,
    }
# ============================================================
# NORMALIZE SOURCE
# ============================================================
def normalize_source(df, columns):
    result = pd.DataFrame()
    result["grid_id"] = df[columns["grid"]].astype(str)
    result["event_time"] = pd.to_datetime(
        df[columns["time"]],
        errors="coerce"
    )
    if result["event_time"].isna().all():
        raise ValueError(
            "The detected time column could not be converted to datetime."
        )
    measure_map = {
        "sms_count": columns["sms"],
        "call_count": columns["calls"],
        "internet_volume": columns["internet"],
    }
    for output_name, source_column in measure_map.items():
        if source_column is None:
            result[output_name] = 0.0
        else:
            result[output_name] = pd.to_numeric(
                df[source_column],
                errors="coerce"
            ).fillna(0.0)
    result["date"] = result["event_time"].dt.strftime(
        "%Y-%m-%d"
    )
    result["hour"] = result["event_time"].dt.hour
    result["day_of_week"] = result["event_time"].dt.day_name()
    return result
# ============================================================
# REFERENCE DATA
# ============================================================
def load_reference_grid_ids():
    if not REFERENCE_FILE.exists():
        print("Reference GeoJSON not found.")
        return {}

    try:
        data = json.loads(
            REFERENCE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        print("Reference GeoJSON could not be read.")
        return {}

    result = {}

    for feature in data.get("features", []):
        properties = feature.get("properties", {})

        grid_id = (
            properties.get("cellId")
            or properties.get("grid_id")
            or properties.get("gridId")
            or properties.get("id")
        )

        if grid_id is None:
            continue

        geometry = feature.get("geometry")

        if not geometry:
            continue

        coordinates = geometry.get("coordinates", [])

        # Polygon geometry:
        # coordinates[0] contains the exterior ring.
        if geometry.get("type") == "Polygon":
            outer_ring = coordinates[0]

            if not outer_ring:
                continue

            longitudes = [
                point[0]
                for point in outer_ring
            ]

            latitudes = [
                point[1]
                for point in outer_ring
            ]

            centroid_longitude = (
                min(longitudes) + max(longitudes)
            ) / 2

            centroid_latitude = (
                min(latitudes) + max(latitudes)
            ) / 2

        else:
            continue

        result[str(grid_id)] = {
            "centroid_latitude":
                centroid_latitude,

            "centroid_longitude":
                centroid_longitude,

            "geometry_reference":
                f"milano-grid.geojson#{grid_id}"
        }

    return result
# ============================================================
# DATABASE
# ============================================================
def create_database():
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()
    connection = sqlite3.connect(DATABASE_FILE)
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE dim_time (
            time_key INTEGER PRIMARY KEY,
            event_date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            day_of_week TEXT NOT NULL,
            UNIQUE(event_date, hour)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE dim_grid (
            grid_key INTEGER PRIMARY KEY AUTOINCREMENT,
            grid_id TEXT NOT NULL UNIQUE,
            centroid_latitude REAL,
            centroid_longitude REAL,
            geometry_reference TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE fact_network_activity (
            fact_key INTEGER PRIMARY KEY AUTOINCREMENT,
            time_key INTEGER NOT NULL,
            grid_key INTEGER NOT NULL,
            grid_id TEXT NOT NULL,
            event_time TEXT NOT NULL,
            sms_count REAL NOT NULL,
            call_count REAL NOT NULL,
            internet_volume REAL NOT NULL,

            FOREIGN KEY(time_key)
                REFERENCES dim_time(time_key),

            FOREIGN KEY(grid_key)
                REFERENCES dim_grid(grid_key)
        )
        """
    )
    connection.commit()
    return connection
# ============================================================
# LOAD DIM TIME
# ============================================================
def load_dim_time(connection, df):
    times = (
        df[
            [
                "date",
                "hour",
                "day_of_week"
            ]
        ]
        .drop_duplicates()
        .sort_values(["date", "hour"])
        .reset_index(drop=True)
    )
    times["time_key"] = range(
        1,
        len(times) + 1
    )
    rows = [
        (
            int(row.time_key),
            row.date,
            int(row.hour),
            row.day_of_week,
        )
        for row in times.itertuples()
    ]
    connection.executemany(
        """
        INSERT INTO dim_time
        (
            time_key,
            event_date,
            hour,
            day_of_week
        )
        VALUES (?, ?, ?, ?)
        """,
        rows
    )
    connection.commit()
    return times
# ============================================================
# LOAD DIM GRID
# ============================================================
def load_dim_grid(connection, df):
    grid_ids = (
        df["grid_id"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    reference = load_reference_grid_ids()
    rows = []
    for grid_id in grid_ids:
        reference_row = reference.get(
            str(grid_id),
            {}
        )
        rows.append(
            (
                str(grid_id),
                reference_row.get("centroid_latitude"),
                reference_row.get("centroid_longitude"),
                reference_row.get("geometry_reference"),
            )
        )
    connection.executemany(
        """
        INSERT INTO dim_grid
        (
            grid_id,
            centroid_latitude,
            centroid_longitude,
            geometry_reference
        )
        VALUES (?, ?, ?, ?)
        """,
        rows
    )
    connection.commit()
    return len(grid_ids)
# ============================================================
# LOAD FACT
# ============================================================
def load_fact(connection, df, dim_time):
    time_lookup = {
        (
            row.date,
            int(row.hour)
        ): int(row.time_key)
        for row in dim_time.itertuples()
    }
    grid_lookup = {}
    rows = connection.execute(
        """
        SELECT grid_key, grid_id
        FROM dim_grid
        """
    ).fetchall()
    for grid_key, grid_id in rows:
        grid_lookup[str(grid_id)] = int(grid_key)
    fact_rows = []
    for row in df.itertuples():
        time_key = time_lookup[
            (
                row.date,
                int(row.hour)
            )
        ]
        grid_key = grid_lookup[
            str(row.grid_id)
        ]
        fact_rows.append(
            (
                time_key,
                grid_key,
                str(row.grid_id),
                row.event_time.isoformat(),
                float(row.sms_count),
                float(row.call_count),
                float(row.internet_volume),
            )
        )
    connection.executemany(
        """
        INSERT INTO fact_network_activity
        (
            time_key,
            grid_key,
            grid_id,
            event_time,
            sms_count,
            call_count,
            internet_volume
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        fact_rows
    )
    connection.commit()
# ============================================================
# INDEXES
# ============================================================
def create_indexes(connection):
    connection.execute(
        """
        CREATE INDEX idx_fact_grid
        ON fact_network_activity(grid_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_fact_time
        ON fact_network_activity(time_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_fact_grid_time
        ON fact_network_activity(grid_key, time_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_fact_event_time
        ON fact_network_activity(event_time)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_dim_grid_id
        ON dim_grid(grid_id)
        """
    )
    connection.commit()
# ============================================================
# VALIDATION
# ============================================================
def validate(connection, source_df):
    results = []
    fact_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM fact_network_activity
        """
    ).fetchone()[0]
    source_count = len(source_df)
    fact_ok = fact_count == source_count
    results.append(
        (
            "Fact row count equals source row count",
            fact_ok,
            f"source={source_count:,}, fact={fact_count:,}"
        )
    )
    distinct_grid_count = (
        source_df["grid_id"]
        .nunique()
    )
    dim_grid_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM dim_grid
        """
    ).fetchone()[0]
    grid_count_ok = (
        distinct_grid_count == dim_grid_count
    )
    results.append(
        (
            "dim_grid count equals distinct grid count",
            grid_count_ok,
            (
                f"source_distinct={distinct_grid_count:,}, "
                f"dim_grid={dim_grid_count:,}"
            )
        )
    )
    duplicate_grids = connection.execute(
        """
        SELECT grid_id, COUNT(*)
        FROM dim_grid
        GROUP BY grid_id
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    results.append(
        (
            "No duplicate dim_grid keys",
            len(duplicate_grids) == 0,
            f"duplicates={len(duplicate_grids)}"
        )
    )
    fact_columns = [
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(fact_network_activity)"
        ).fetchall()
    ]
    geometry_absent = (
        "geometry" not in fact_columns
        and "geometry_reference" not in fact_columns
    )
    results.append(
        (
            "fact_network_activity contains no geometry",
            geometry_absent,
            "geometry column absent"
        )
    )
    # --------------------------------------------------------
    # Source aggregate
    # --------------------------------------------------------
    source_sms = float(
        source_df["sms_count"].sum()
    )
    source_calls = float(
        source_df["call_count"].sum()
    )
    source_internet = float(
        source_df["internet_volume"].sum()
    )
    # --------------------------------------------------------
    # SQL aggregate
    # --------------------------------------------------------
    sql_result = connection.execute(
        """
        SELECT
            SUM(sms_count),
            SUM(call_count),
            SUM(internet_volume)
        FROM fact_network_activity
        """
    ).fetchone()
    sql_sms = float(sql_result[0] or 0)
    sql_calls = float(sql_result[1] or 0)
    sql_internet = float(sql_result[2] or 0)
    aggregate_ok = (
        source_sms == sql_sms
        and source_calls == sql_calls
        and source_internet == sql_internet
    )
    results.append(
        (
            "SQL aggregate exactly matches source aggregate",
            aggregate_ok,
            (
                f"SMS={sql_sms}, "
                f"CALLS={sql_calls}, "
                f"INTERNET={sql_internet}"
            )
        )
    )
    # --------------------------------------------------------
    # Index validation
    # --------------------------------------------------------
    indexes = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index'
        """
    ).fetchall()
    index_names = {
        row[0]
        for row in indexes
    }
    required_indexes = {
        "idx_fact_grid",
        "idx_fact_time",
        "idx_fact_grid_time",
        "idx_fact_event_time",
    }
    index_ok = required_indexes.issubset(
        index_names
    )
    results.append(
        (
            "Required analytical indexes exist",
            index_ok,
            ", ".join(sorted(index_names))
        )
    )
    return results
# ============================================================
# SAMPLE QUERIES
# ============================================================
def write_sample_queries():
    queries = """
-- ============================================================
-- Warehouse Modelling for Network Analytics
-- Sample Analytical Queries
-- ============================================================

-- 1. TOP GRIDS BY TOTAL ACTIVITY

SELECT
    g.grid_id,
    SUM(f.sms_count) AS total_sms,
    SUM(f.call_count) AS total_calls,
    SUM(f.internet_volume) AS total_internet
FROM fact_network_activity f
JOIN dim_grid g
    ON f.grid_key = g.grid_key
GROUP BY g.grid_id
ORDER BY
    (
        total_sms
        + total_calls
        + total_internet
    ) DESC
LIMIT 10;


-- 2. HOURLY ACTIVITY TREND

SELECT
    t.event_date,
    t.hour,
    SUM(f.sms_count) AS total_sms,
    SUM(f.call_count) AS total_calls,
    SUM(f.internet_volume) AS total_internet
FROM fact_network_activity f
JOIN dim_time t
    ON f.time_key = t.time_key
GROUP BY
    t.event_date,
    t.hour
ORDER BY
    t.event_date,
    t.hour;


-- 3. INTERNET-HEAVY WINDOWS

SELECT
    t.event_date,
    t.hour,
    SUM(f.internet_volume) AS total_internet
FROM fact_network_activity f
JOIN dim_time t
    ON f.time_key = t.time_key
GROUP BY
    t.event_date,
    t.hour
ORDER BY
    total_internet DESC
LIMIT 10;


-- 4. VERIFY FACT ROW COUNT

SELECT COUNT(*) AS fact_row_count
FROM fact_network_activity;


-- 5. VERIFY GRID DIMENSION

SELECT COUNT(*) AS grid_dimension_count
FROM dim_grid;

-- 6. CHECK DUPLICATE GRID KEYS

SELECT
    grid_id,
    COUNT(*) AS duplicate_count
FROM dim_grid
GROUP BY grid_id
HAVING COUNT(*) > 1;

-- 7. VERIFY THAT FACT HAS NO GEOMETRY

PRAGMA table_info(fact_network_activity);
"""

    SQL_FILE.write_text(
        queries.strip() + "\n",
        encoding="utf-8"
    )
# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("=" * 70)
    print(LAB_NAME)
    print("=" * 70)
    source = load_source()
    columns = detect_columns(source)
    print()
    print("Detected columns")
    print("-" * 70)
    for name, column in columns.items():
        print(f"{name:20} : {column}")
    normalized = normalize_source(
        source,
        columns
    )
    connection = create_database()
    try:
        dim_time = load_dim_time(
            connection,
            normalized
        )
        dim_grid_count = load_dim_grid(
            connection,
            normalized
        )
        load_fact(
            connection,
            normalized,
            dim_time
        )
        create_indexes(
            connection
        )
        pd.read_sql_query("SELECT * FROM fact_network_activity", connection).to_csv(OUTPUT_DIR / "fact_network_activity.csv", index=False)
        pd.read_sql_query("SELECT * FROM dim_time", connection).to_csv(OUTPUT_DIR / "dim_time.csv", index=False)
        pd.read_sql_query("SELECT * FROM dim_grid", connection).to_csv(OUTPUT_DIR / "dim_grid.csv", index=False)
        validation = validate(
            connection,
            normalized
        )
        write_sample_queries()
        with VALIDATION_FILE.open(
            "w",
            encoding="utf-8"
        ) as file:
            file.write(
                f"{LAB_NAME}\n"
            )
            file.write(
                "=" * 70 + "\n\n"
            )
            for name, passed, details in validation:
                status = (
                    "PASS"
                    if passed
                    else "FAIL"
                )
                file.write(
                    f"[{status}] {name}\n"
                )
                file.write(
                    f"       {details}\n"
                )
        print()
        print("WAREHOUSE TABLES")
        print("-" * 70)
        for table in [
            "dim_time",
            "dim_grid",
            "fact_network_activity"
        ]:
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            print(
                f"{table:30} {count:,} rows"
            )
        print()
        print("ACCEPTANCE CRITERIA")
        print("=" * 70)
        all_passed = True
        for name, passed, details in validation:
            print(
                f"[{'PASS' if passed else 'FAIL'}] "
                f"{name}"
            )
            if not passed:
                all_passed = False
        print()
        print("OUTPUT FILES")
        print("=" * 70)
        print(DATABASE_FILE)
        print(VALIDATION_FILE)
        print(SQL_FILE)
        print()
        print("SAMPLE QUERY: TOP 5 GRIDS")
        print("-" * 70)
        rows = connection.execute(
            """
            SELECT
                g.grid_id,
                SUM(f.internet_volume) AS internet_volume
            FROM fact_network_activity f
            JOIN dim_grid g
                ON f.grid_key = g.grid_key
            GROUP BY g.grid_id
            ORDER BY internet_volume DESC
            LIMIT 5
            """
        ).fetchall()
        for grid_id, internet in rows:
            print(
                f"grid_id={grid_id}, "
                f"internet={internet}"
            )
        print()
        if all_passed:
            print(
                f"{LAB_NAME} completed successfully."
            )
        else:
            print(
                f"{LAB_NAME} completed with validation failures."
            )
            sys.exit(1)
    finally:
        connection.close()
if __name__ == "__main__":
    main()