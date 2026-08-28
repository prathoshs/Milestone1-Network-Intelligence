import os
from pathlib import Path
os.environ["HADOOP_HOME"] = (
    r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
)
os.environ["PATH"] += (
    r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
)
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum,to_date, hour, desc
)
# ============================================================
# CONFIG
# ============================================================
BASE = Path(__file__).resolve().parent
INPUT = BASE / "parquet_output" / "raw_parquet"
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)
# ============================================================
# SPARK
# ============================================================
spark = (
    SparkSession.builder
    .appName("NetworkProject")
    .master("local[*]")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
# ============================================================
# READ SP1 PARQUET
# ============================================================
raw_df = spark.read.parquet(str(INPUT))
# SP1 already created the hourly timestamp column "hour".
# Use it as the canonical hourly timestamp.
clean_network_df = (
    raw_df
    .withColumnRenamed("CellID", "grid_id")
    .withColumnRenamed("countrycode", "country_code")
    .withColumnRenamed("smsin", "sms_in")
    .withColumnRenamed("smsout", "sms_out")
    .withColumnRenamed("callin", "call_in")
    .withColumnRenamed("callout", "call_out")
    .withColumnRenamed("internet", "internet_activity")
    .withColumnRenamed("hour", "timestamp")
)
# ============================================================
# COUNTRY → GRID/HOUR AGGREGATION
# ============================================================
hourly_grid_summary = (
    clean_network_df
    .groupBy("grid_id", "timestamp")
    .agg(
        sum("sms_in").alias("sms_in"),
        sum("sms_out").alias("sms_out"),
        sum("call_in").alias("call_in"),
        sum("call_out").alias("call_out"),
        sum("internet_activity").alias("internet_activity")
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
# ============================================================
# ACCEPTANCE CHECK 1 — NO DUPLICATES
# ============================================================
duplicates = (
    hourly_grid_summary
    .groupBy("grid_id", "timestamp")
    .count()
    .filter(col("count") > 1)
    .count()
)
assert duplicates == 0, (
    f"Duplicate grid/hour records found: {duplicates}"
)
# ============================================================
# ACCEPTANCE CHECK 2 — GRAIN REDUCTION
# ============================================================
clean_count = clean_network_df.count()
hourly_count = hourly_grid_summary.count()
assert hourly_count < clean_count, (
    f"Aggregation did not reduce rows: "
    f"clean={clean_count}, hourly={hourly_count}"
)
# ============================================================
# ACCEPTANCE CHECK 3 — MAXIMUM GRAIN
# ============================================================
days = hourly_grid_summary.select("date").distinct().count()
max_rows = days * 24 * 10000
assert hourly_count <= max_rows, (
    f"Hourly rows exceed maximum: "
    f"{hourly_count} > {max_rows}"
)
# ============================================================
# ACCEPTANCE CHECK 4 — HAND CHECK ONE GRID/HOUR
# ============================================================
sample = (
    clean_network_df
    .select("grid_id", "timestamp", "sms_in")
    .groupBy("grid_id", "timestamp")
    .agg(sum("sms_in").alias("expected_sms_in"))
    .first()
)
actual = (
    hourly_grid_summary
    .filter(
        (col("grid_id") == sample["grid_id"]) &
        (col("timestamp") == sample["timestamp"])
    )
    .select("sms_in")
    .first()["sms_in"]
)
assert float(actual) == float(sample["expected_sms_in"]), (
    "Hand-check aggregation failed"
)
# ============================================================
# ACCEPTANCE CHECK 5 — COUNTRY CODE ABSENT
# ============================================================
assert "country_code" not in hourly_grid_summary.columns
# ============================================================
# DAILY TRAFFIC SUMMARY
# ============================================================
daily_traffic_summary = (
    hourly_grid_summary
    .groupBy("date", "grid_id")
    .agg(
        sum("total_sms").alias("total_sms"),
        sum("total_calls").alias("total_calls"),
        sum("internet_activity").alias("internet_activity"),
        sum("total_activity").alias("total_activity")
    )
)
# ============================================================
# TOP 10 HOTSPOTS
# ============================================================
hotspot_ranking = (
    daily_traffic_summary
    .groupBy("grid_id")
    .agg(
        sum("total_activity").alias("total_activity")
    )
    .orderBy(desc("total_activity"))
    .limit(10)
)
# ============================================================
# PEAK ACTIVITY HOUR
# ============================================================
peak_activity_hour = (
    hourly_grid_summary
    .groupBy(hour("timestamp").alias("hour"))
    .agg(
        sum("total_activity").alias("total_activity")
    )
    .orderBy(desc("total_activity"))
    .limit(1)
)
# ============================================================
# INTERNET SHARE
# ============================================================
internet_share = (
    hourly_grid_summary
    .agg(
        (
            sum("internet_activity")
            / sum("total_activity") * 100
        ).alias("internet_share_percent")
    )
)
# ============================================================
# WRITE OUTPUTS
# ============================================================
hourly_grid_summary.write.mode("overwrite").parquet(
    str(OUT / "hourly_grid_summary")
)

daily_traffic_summary.write.mode("overwrite").parquet(
    str(OUT / "daily_traffic_summary")
)

hotspot_ranking.coalesce(1).write.mode("overwrite").option(
    "header", True
).csv(str(OUT / "hotspot_ranking"))
# ============================================================
# OUTPUT
# ============================================================
print("\n================= AGGREGATION SUMMARY =====================")
print(f"Clean input rows       : {clean_count:,}")
print(f"Hourly summary rows    : {hourly_count:,}")
print(f"Days                   : {days}")
print(f"Maximum allowed rows   : {max_rows:,}")
print(f"Duplicate grid-hours   : {duplicates}")
print("Country code present   : NO")
print("Grain validation       : PASS")
print("Hand-check             : PASS")
print("="*60)
print("\nTop 10 hotspots:")
hotspot_ranking.show(10, truncate=False)

print("\nPeak activity hour:")
peak_activity_hour.show(truncate=False)

print("\nInternet share:")
internet_share.show(truncate=False)

print("\nCOMPLETE")

spark.stop()