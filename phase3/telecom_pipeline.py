import argparse
import glob
import logging
import os
from datetime import datetime
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    trim,
    when,
    lit,
    to_timestamp,
    to_date,
    hour,
    dayofweek,
    sum as Fsum,
    input_file_name,
    broadcast,
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
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
    "internet_activity",
]

RENAME = {
    "datetime": "timestamp",
    "CellID": "grid_id",
    "countrycode": "country_code",
    "smsin": "sms_in",
    "smsout": "sms_out",
    "callin": "call_in",
    "callout": "call_out",
    "internet": "internet_activity",
}


# ============================================================
# READ
# ============================================================

def read_raw(spark, input_path):
    files = sorted(
        glob.glob(
            os.path.join(
                input_path,
                "sms-call-internet-mi-*.csv",
            )
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
        .withColumn(
            "input_file_name",
            input_file_name(),
        )
    )

    input_rows = df.count()
    log.info("INPUT_ROWS=%d", input_rows)

    return df


# ============================================================
# CLEAN
# ============================================================

def clean(df):
    raw_count = df.count()

    for old, new in RENAME.items():
        if old in df.columns:
            df = df.withColumnRenamed(old, new)

    required = [
        "timestamp",
        "grid_id",
        "country_code",
        "sms_in",
        "sms_out",
        "call_in",
        "call_out",
        "internet_activity",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    df = df.withColumn(
        "timestamp",
        to_timestamp(
            trim(col("timestamp"))
        ),
    )

    numeric_columns = [
        "sms_in",
        "sms_out",
        "call_in",
        "call_out",
        "internet_activity",
    ]

    for c in numeric_columns:
        df = df.withColumn(
            c,
            when(
                col(c).isNull(),
                lit(0),
            ).otherwise(col(c)),
        )

    nulls_after = df.select(
        *[
            Fsum(
                when(col(c).isNull(), 1)
                .otherwise(0)
            ).alias(c)
            for c in required
        ]
    ).collect()[0]

    nulls_handled = sum(
        value or 0
        for value in nulls_after
    )

    df = df.filter(
        col("timestamp").isNotNull()
    )

    df = df.filter(
        (col("sms_in") >= 0)
        & (col("sms_out") >= 0)
        & (col("call_in") >= 0)
        & (col("call_out") >= 0)
        & (col("internet_activity") >= 0)
    )

    df = (
        df.withColumn(
            "total_sms",
            col("sms_in") + col("sms_out"),
        )
        .withColumn(
            "total_calls",
            col("call_in") + col("call_out"),
        )
        .withColumn(
            "total_activity",
            col("total_sms")
            + col("total_calls")
            + col("internet_activity"),
        )
        .withColumn(
            "date",
            to_date(col("timestamp")),
        )
        .withColumn(
            "hour",
            hour(col("timestamp")),
        )
        .withColumn(
            "day_of_week",
            dayofweek(col("timestamp")),
        )
        .withColumn(
            "hour_timestamp",
            col("timestamp"),
        )
    )

    clean_count = df.count()
    rejected = raw_count - clean_count

    log.info("REJECTED_ROWS=%d", rejected)
    log.info("NULLS_HANDLED=%d", nulls_handled)
    log.info("OUTPUT_ROWS=%d", clean_count)

    return df, raw_count, rejected, clean_count, nulls_handled


# ============================================================
# AGGREGATE
# ============================================================

def aggregate(clean_df):
    hourly = (
        clean_df
        .groupBy(
            "grid_id",
            "hour_timestamp",
            "date",
        )
        .agg(
            Fsum("sms_in").alias("sms_in"),
            Fsum("sms_out").alias("sms_out"),
            Fsum("call_in").alias("call_in"),
            Fsum("call_out").alias("call_out"),
            Fsum(
                "internet_activity"
            ).alias("internet_activity"),
            Fsum(
                "total_sms"
            ).alias("total_sms"),
            Fsum(
                "total_calls"
            ).alias("total_calls"),
            Fsum(
                "total_activity"
            ).alias("total_activity"),
        )
        .withColumnRenamed(
            "hour_timestamp",
            "timestamp",
        )
    )

    output_count = hourly.count()

    log.info(
        "AGGREGATED_ROWS=%d",
        output_count,
    )

    return hourly


# ============================================================
# ENRICH
# ============================================================

def enrich(spark, hourly, reference_path):
    if not os.path.exists(reference_path):
        raise FileNotFoundError(
            f"GeoJSON reference not found: {reference_path}"
        )

    reference = (
        spark.read
        .json(reference_path)
    )

    log.info(
        "REFERENCE_PATH=%s",
        reference_path,
    )

    reference_columns = reference.columns

    # Join when a compatible grid identifier exists.
    if "grid_id" in reference_columns:
        enriched = hourly.join(
            broadcast(reference),
            on="grid_id",
            how="left",
        )
    else:
        log.warning(
            "Reference file has no grid_id column; "
            "continuing without reference join."
        )
        enriched = hourly

    return enriched


# ============================================================
# WRITE
# ============================================================

def write_outputs(
    clean_df,
    hourly_df,
    enriched_df,
    processed_path,
    analytics_path,
):
    processed = Path(processed_path)
    analytics = Path(analytics_path)

    processed.mkdir(
        parents=True,
        exist_ok=True,
    )

    analytics.mkdir(
        parents=True,
        exist_ok=True,
    )
    # --------------------------------------------------------
    # PROCESSED
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
            "hour_timestamp",
        )
        .repartition(7, "date")
    )
    clean_write.write \
        .mode("overwrite") \
        .partitionBy("date") \
        .parquet(str(processed / "activity"))
    log.info(
        "PROCESSED_OUTPUT=%s",
        processed / "activity",
    )
    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------
    enriched_write = (
        enriched_df
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
            "date",
        )
        .repartition(8, "date")
    )
    enriched_write.write \
        .mode("overwrite") \
        .parquet(
            str(
                analytics
                / "hourly_grid_summary"
            )
        )
    log.info(
        "ANALYTICS_OUTPUT=%s",
        analytics / "hourly_grid_summary",
    )
    # --------------------------------------------------------
    # DASHBOARD SUMMARY
    # --------------------------------------------------------
    dashboard = (
        hourly_df
        .groupBy("date")
        .agg(
            Fsum("sms_in").alias("sms_in"),
            Fsum("sms_out").alias("sms_out"),
            Fsum("call_in").alias("call_in"),
            Fsum("call_out").alias("call_out"),
            Fsum(
                "internet_activity"
            ).alias("internet_activity"),
            Fsum(
                "total_activity"
            ).alias("total_activity"),
        )
        .orderBy("date")
    )
    dashboard.write \
        .mode("overwrite") \
        .option("header", True) \
        .csv(
            str(
                analytics
                / "dashboard_summary"
            )
        )
    log.info(
        "DASHBOARD_OUTPUT=%s",
        analytics / "dashboard_summary",
    )
# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Reusable Telecom Spark ETL Job"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Raw input directory",
    )
    parser.add_argument(
        "--processed",
        required=True,
        help="Processed output directory",
    )
    parser.add_argument(
        "--analytics",
        required=True,
        help="Analytics output directory",
    )
    parser.add_argument(
        "--reference",
        required=True,
        help="Path to milano-grid.geojson",
    )
    args = parser.parse_args()
    start = datetime.now()
    log.info(
        "START_TIME=%s",
        start.isoformat(),
    )
    spark = None
    try:
        spark = (
            SparkSession.builder
            .appName("TelecomETL")
            .master("local[4]")
            .config(
                "spark.sql.shuffle.partitions",
                "8",
            )
            .config(
                "spark.default.parallelism",
                "8",
            )
            .config(
                "spark.sql.files.maxPartitionBytes",
                "64m",
            )
            .config(
                "spark.sql.parquet.compression.codec",
                "snappy",
            )
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")
        raw = read_raw(
            spark,
            args.input,
        )
        clean_df, raw_count, rejected, clean_count, nulls = clean(
            raw
        )
        hourly = aggregate(clean_df)
        enriched = enrich(
            spark,
            hourly,
            args.reference,
        )
        write_outputs(
            clean_df,
            hourly,
            enriched,
            args.processed,
            args.analytics,
        )
        end = datetime.now()
        log.info(
            "END_TIME=%s",
            end.isoformat(),
        )
        log.info(
            "STATUS=SUCCESS"
        )
    except Exception:
        log.exception(
            "STATUS=FAILED"
        )
        raise
    finally:
        if spark is not None:
            spark.stop()
if __name__ == "__main__":
    main()