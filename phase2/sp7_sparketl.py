import os
import sys
import glob
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, trim, when, lit, to_timestamp, to_date,
    hour, dayofweek, sum as Fsum, input_file_name,
    countDistinct, broadcast
)
os.environ["HADOOP_HOME"] = (
    r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
)
os.environ["PATH"] += (
    r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
)
# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("TelecomETL")
# ============================================================
# CONSTANTS
# ============================================================
ACTIVITY = [
    "sms_in",
    "sms_out",
    "call_in",
    "call_out",
    "internet_activity"
]
RENAME = {
    "datetime": "timestamp",
    "CellID": "grid_id",
    "countrycode": "country_code",
    "smsin": "sms_in",
    "smsout": "sms_out",
    "callin": "call_in",
    "callout": "call_out",
    "internet": "internet_activity"
}
# ============================================================
# READ
# ============================================================
def read_raw(spark, input_path):
    files = sorted(
        glob.glob(
            os.path.join(input_path, "sms-call-internet-mi-*.csv")
        )
    )
    if not files:
        raise FileNotFoundError(
            f"No input files found in: {input_path}"
           )
    log.info("INPUT_FILES=%d", len(files))
    df = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .csv(files)
        .withColumn("input_file_name", input_file_name())
    )
    return df
# ============================================================
# CLEAN
# ============================================================
def clean(df):
    raw_count = df.count()
    for old, new in RENAME.items():
        if old in df.columns:
            df = df.withColumnRenamed(old, new)
    # Normalize grid_id BEFORE any validation/comparison.
    df = df.withColumn(
        "grid_id",
        when(
            trim(col("grid_id")).isin("", "null", "NULL"),
            None
        ).otherwise(trim(col("grid_id")))
    )
    df = df.withColumn(
        "timestamp",
        to_timestamp(col("timestamp"))
    )
    for c in ACTIVITY:
        df = df.withColumn(
            c,
            col(c).cast("double")
        )
    # Profile nulls BEFORE replacing them with zero.
    null_expr = [
        Fsum(
            when(col(c).isNull(), 1).otherwise(0)
        ).alias(c)
        for c in ACTIVITY
    ]
    null_row = df.agg(*null_expr).first()
    null_counts = {
        c: int(null_row[c] or 0)
        for c in ACTIVITY
    }
    null_handled = sum(null_counts.values())
    # Invalid records.
    bad = (
        col("grid_id").isNull()
        | (trim(col("grid_id")) == "")
        | col("timestamp").isNull()
    )
    for c in ACTIVITY:
        bad = bad | (
            col(c).isNotNull() & (col(c) < 0)
        )
    rejected_count = df.filter(bad).count()
    # Keep valid records.
    df = df.filter(~bad)
    # Curated null -> zero.
    for c in ACTIVITY:
        df = df.withColumn(
            c,
            when(col(c).isNull(), lit(0.0))
            .otherwise(col(c))
        )
    # Derived fields.
    df = (
        df
        .withColumn(
            "total_sms",
            col("sms_in") + col("sms_out")
        )
        .withColumn(
            "total_calls",
            col("call_in") + col("call_out")
        )
        .withColumn(
            "total_activity",
            col("total_sms")
            + col("total_calls")
            + col("internet_activity")
        )
        .withColumn("date", to_date("timestamp"))
        .withColumn("hour", hour("timestamp"))
        .withColumn("day_of_week", dayofweek("timestamp"))
        .withColumn(
            "hour_timestamp",
            to_timestamp(
                col("timestamp").cast("string")
            )
        )
    )
    clean_count = df.count()
    if raw_count != rejected_count + clean_count:
        raise ValueError(
            f"ROW_COUNT_MISMATCH: "
            f"RAW={raw_count}, "
            f"REJECTED={rejected_count}, "
            f"CLEAN={clean_count}"
        )
    log.info("INPUT_ROWS=%d", raw_count)
    log.info("REJECTED_ROWS=%d", rejected_count)
    log.info("NULLS_HANDLED=%d", null_handled)
    return df, raw_count, rejected_count, clean_count, null_counts
# ============================================================
# AGGREGATE
# ============================================================
def aggregate(clean_df):
    hourly = (
        clean_df
        .groupBy("grid_id", "timestamp")
        .agg(
            Fsum("sms_in").alias("sms_in"),
            Fsum("sms_out").alias("sms_out"),
            Fsum("call_in").alias("call_in"),
            Fsum("call_out").alias("call_out"),
            Fsum("internet_activity").alias(
                "internet_activity"
            )
        )
        .withColumn(
            "total_sms",
            col("sms_in") + col("sms_out")
        )
        .withColumn(
            "total_calls",
            col("call_in") + col("call_out")
        )
        .withColumn(
            "total_activity",
            col("total_sms")
            + col("total_calls")
            + col("internet_activity")
        )
        .withColumn("date", to_date("timestamp"))
    )
    # Required grain validation.
    duplicates = (
        hourly
        .groupBy("grid_id", "timestamp")
        .count()
        .filter(col("count") > 1)
        .count()
    )
    if duplicates != 0:
        raise ValueError(
            f"DUPLICATE_GRID_HOURS={duplicates}"
        )
    output_count = hourly.count()
    input_count = clean_df.count()
    if output_count >= input_count:
        raise ValueError(
            f"AGGREGATION_DID_NOT_REDUCE_ROWS: "
            f"INPUT={input_count}, OUTPUT={output_count}"
        )
    log.info("OUTPUT_ROWS=%d", output_count)
    return hourly
# ============================================================
# GEOJSON ENRICHMENT
# ============================================================
def enrich(spark, hourly, reference_path):
    if not os.path.exists(reference_path):
        raise FileNotFoundError(
            f"GeoJSON reference not found: {reference_path}"
        )
    # GeoJSON is a FeatureCollection.
    geo_raw = spark.read.option(
        "multiLine", True
    ).json(reference_path)
    if "features" not in geo_raw.columns:
        raise ValueError(
            "Invalid GeoJSON: features array not found"
        )
    # IMPORTANT:
    # Use properties.cellId, NOT feature["id"].
    lookup_df = (
        geo_raw
        .selectExpr(
            "explode(features) AS feature"
        )
        .select(
            col("feature.properties.cellId")
            .cast("long")
            .alias("geo_grid_id"),

            col("feature.geometry")
            .alias("geometry")
        )
        .dropDuplicates(["geo_grid_id"])
    )
    lookup_count = lookup_df.count()
    if lookup_count != 10000:
        raise ValueError(
            f"Expected 10000 grid cells, found {lookup_count}"
        )
    print(f"Grid lookup rows    : {lookup_count:,}")
    activity = hourly.withColumn(
        "activity_grid_id",
        col("grid_id").cast("long")
    )
    # Broadcast the small 10,000-row reference table.
    enriched = (
        activity.alias("a")
        .join(
            broadcast(lookup_df).alias("g"),
            col("a.activity_grid_id")
            == col("g.geo_grid_id"),
            "left"
        )
        .select(
            col("a.grid_id").alias("grid_id"),
            col("a.timestamp"),
            col("a.sms_in"),
            col("a.sms_out"),
            col("a.call_in"),
            col("a.call_out"),
            col("a.internet_activity"),
            col("a.total_sms"),
            col("a.total_calls"),
            col("a.total_activity"),
            col("a.date"),
            col("g.geometry")
        )
    )
    # -------------------------------
    # JOIN VALIDATION
    # -------------------------------
    before = (
        hourly
        .select("grid_id")
        .distinct()
        .count()
    )
    after = (
        enriched
        .select("grid_id")
        .distinct()
        .count()
    )
    missing = (
        enriched
        .filter(col("geometry").isNull())
        .select("grid_id")
        .distinct()
        .count()
    )
    rows_before = hourly.count()
    rows_after = enriched.count()
    coverage = (
        (before - missing) / before * 100
        if before else 0
    )
    print("\n========== GEO JOIN VALIDATION ==========")
    print(f"Distinct grids before : {before:,}")
    print(f"Distinct grids after  : {after:,}")
    print(f"Missing geometries    : {missing:,}")
    print(f"Coverage              : {coverage:.2f}%")
    print(f"Rows before join      : {rows_before:,}")
    print(f"Rows after join       : {rows_after:,}")
    if missing > 0:
        print("\nUnmatched grid IDs:")
        (
            enriched
            .filter(col("geometry").isNull())
            .select("grid_id")
            .distinct()
            .orderBy("grid_id")
            .show(20, truncate=False)
        )
        raise ValueError(
            f"GEOSPATIAL_ENRICHMENT_FAILED: "
            f"{missing} unmatched grids"
        )
    if rows_before != rows_after:
        raise ValueError(
            f"JOIN_MULTIPLIED_ROWS: "
            f"{rows_before} -> {rows_after}"
        )
    if coverage != 100:
        raise ValueError(
            f"ENRICHMENT_COVERAGE_FAILED: "
            f"{coverage:.2f}%"
        )
    print("Unmatched grids      : 0")
    print("Row count check      : PASS")
    print("Coverage check       : PASS")
    return enriched
print("="*50)
# ============================================================
# WRITE
# ============================================================
def write_outputs(clean_df, hourly_df, reference_path, output_path):
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    processed = output / "data" / "processed" / "activity"
    analytics = output / "data" / "analytics" / "hourly_grid_summary"
    dashboard = output / "data" / "analytics" / "dashboard_summary.csv"
    # --------------------------------------------------------
    # CLEAN ACTIVITY
    # --------------------------------------------------------
    clean_write = (
        clean_df
        .select(
            "timestamp",
            "grid_id",
            "country_code",
            "sms_in",
            "sms_out",
            "call_in",
            "call_out",
            "internet_activity",
            "total_sms",
            "total_calls",
            "total_activity",
            "date",
            "hour",
            "day_of_week",
            "hour_timestamp"
        )
        .repartition(7, "date")
    )
    clean_write.write \
        .mode("overwrite") \
        .partitionBy("date") \
        .parquet(str(processed))
    print(f"Clean activity written: {processed}")
    # --------------------------------------------------------
    # HOURLY ANALYTICS
    # --------------------------------------------------------
    hourly_write = (
        hourly_df
        .select(
            "grid_id",
            "timestamp",
            "sms_in",
            "sms_out",
            "call_in",
            "call_out",
            "internet_activity",
            "total_sms",
            "total_calls",
            "total_activity",
            "date"
        )
        .repartition(8, "date")
    )
    hourly_write.write \
        .mode("overwrite") \
        .parquet(str(analytics))
    print(f"Hourly analytics written: {analytics}")
    # --------------------------------------------------------
    # SMALL DASHBOARD SUMMARY
    # --------------------------------------------------------
    dashboard_df = (
        hourly_df
        .groupBy("date")
        .agg(
            Fsum("sms_in").alias("sms_in"),
            Fsum("sms_out").alias("sms_out"),
            Fsum("call_in").alias("call_in"),
            Fsum("call_out").alias("call_out"),
            Fsum("internet_activity").alias(
                "internet_activity"
            ),
            Fsum("total_activity").alias(
                "total_activity"
            )
        )
        .orderBy("date")
    )
    dashboard_df.coalesce(1) \
        .write \
        .mode("overwrite") \
        .option("header", True) \
        .csv(str(dashboard))
    print(f"Dashboard summary written: {dashboard}")
# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Reusable Telecom Spark ETL Job"
    )
    parser.add_argument(
    "--input",
    default=str(Path(__file__).resolve().parent.parent / "dataset"),
    help="Folder containing daily CSV files"
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "data"),
        help="Output root folder"
    )
    parser.add_argument(
        "--reference",
        default=str(
        Path(__file__).resolve().parent.parent
        / "dataset"
        / "milano-grid.geojson"
    ),
    help="Path to milano-grid.geojson"
    )
    args = parser.parse_args()
    start = datetime.now()
    log.info(
        "START_TIME=%s",
        start.isoformat()
    )
    spark = None
    try:
        spark = (
            SparkSession.builder
            .appName("TelecomETL")
            .master("local[4]")
            .config("spark.driver.memory", "4g")
            .config("spark.executor.memory", "4g")
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.default.parallelism", "8")
            .config("spark.sql.files.maxPartitionBytes", "64m")
            .config("spark.sql.parquet.compression.codec", "snappy")
            .config("spark.network.timeout", "300s")
            .config("spark.executor.heartbeatInterval", "30s")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")
        raw = read_raw(
            spark,
            args.input
        )
        clean_df, raw_count, rejected, clean_count, nulls = clean(
            raw
        )
        hourly = aggregate(
            clean_df
        )
        enriched = enrich(
            spark,
            hourly,
            args.reference
        )
        write_outputs(
            clean_df,
            hourly,
            enriched,
            args.output
        )
        end = datetime.now()
        log.info(
            "END_TIME=%s",
            end.isoformat()
        )
        log.info(
            "STATUS=SUCCESS"
        )
        print("\n======================================")
        print("       TELECOM ETL PIPELINE")
        print("======================================")
        print(f"Input rows       : {raw_count:,}")
        print(f"Rejected rows    : {rejected:,}")
        print(f"Clean rows       : {clean_count:,}")
        print(
            f"Nulls handled    : {sum(nulls.values()):,}"
        )
        print(
            f"Hourly rows      : {hourly.count():,}"
        )
        print(
            "Geospatial       : 100% enriched"
        )
        print("Status           : SUCCESS")
        print("======================================")
    except Exception as e:
        log.error(
            "STATUS=FAILED | ERROR=%s",
            str(e)
        )
        print("\n======================================")
        print("       TELECOM ETL PIPELINE FAILED")
        print("======================================")
        print(f"ERROR: {e}")
        print("======================================")
        sys.exit(1)
    finally:
        if spark is not None:
            spark.stop()

if __name__ == "__main__":
    main()