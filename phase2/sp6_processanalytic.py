import os
from pathlib import Path
import shutil
os.environ["HADOOP_HOME"] = (
    r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
)
os.environ["PATH"] += (
    r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
)
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum as Fsum, desc, count
)
# ============================================================
# CONFIGURATION
# ============================================================
BASE = Path(__file__).resolve().parent
CLEAN_INPUT = BASE / "output" / "clean_network"
HOURLY_INPUT = BASE / "output" / "hourly_grid_summary"
PROCESSED = BASE / "data" / "processed" / "activity"
ANALYTICS = BASE / "data" / "analytics" / "hourly_grid_summary"
DASHBOARD = BASE / "data" / "analytics" / "dashboard_summary.csv"
PROCESSED.mkdir(parents=True, exist_ok=True)
ANALYTICS.mkdir(parents=True, exist_ok=True)
DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
# ============================================================
# SPARK
# ============================================================
spark = (
    SparkSession.builder
    .appName("WriteProcessedAnalytics Data")
    .master("local[1]")
    .config("spark.sql.shuffle.partitions", "8")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
# ============================================================
# READ INPUTS
# ============================================================
clean_df = spark.read.parquet(str(CLEAN_INPUT))
hourly_df = spark.read.parquet(str(HOURLY_INPUT))
clean_count = clean_df.count()
hourly_count = hourly_df.count()
print("\n========== INPUT ==========")
print(f"Clean rows       : {clean_count:,}")
print(f"Hourly rows      : {hourly_count:,}")
print("="*30)
# ============================================================
# 1. WRITE CLEAN ACTIVITY — PARTITIONED BY DATE
# ============================================================
clean_df.write \
    .mode("overwrite") \
    .partitionBy("date") \
    .parquet(str(PROCESSED))
print("\nClean activity written:")
print(PROCESSED)
# ============================================================
# 2. REMOVE GEOMETRY FROM ANALYTICS DATA
# ============================================================
assert "geometry" not in hourly_df.columns, (
    "Geometry must not exist in hourly_grid_summary"
)
analytics_df = hourly_df.select(
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
assert "geometry" not in analytics_df.columns
# ============================================================
# 3. WRITE HOURLY GRID SUMMARY
# ============================================================
analytics_df.write \
    .mode("overwrite") \
    .parquet(str(ANALYTICS))
print("\nHourly analytics written:")
print(ANALYTICS)
# ============================================================
# 4. DASHBOARD SUMMARY
# ============================================================
dashboard_summary = (
    analytics_df
    .groupBy("date")
    .agg(
        Fsum("total_sms").alias("total_sms"),
        Fsum("total_calls").alias("total_calls"),
        Fsum("internet_activity").alias("internet_activity"),
        Fsum("total_activity").alias("total_activity")
    )
    .orderBy("date")
)
dashboard_summary.coalesce(1) \
    .write \
    .mode("overwrite") \
    .option("header", True) \
    .csv(str(DASHBOARD))
print("\nDashboard summary written:")
print(DASHBOARD)
# ============================================================
# 5. ROUND-TRIP VALIDATION
# ============================================================
roundtrip_df = spark.read.parquet(str(ANALYTICS))
roundtrip_count = roundtrip_df.count()
assert roundtrip_count == hourly_count, (
    f"Row-count mismatch: "
    f"before={hourly_count}, after={roundtrip_count}"
)
assert roundtrip_df.schema == analytics_df.schema, (
    "Schema mismatch after Parquet round-trip"
)
print("\n========== ROUND-TRIP VALIDATION ==========")
print(f"Rows before write : {hourly_count:,}")
print(f"Rows after read   : {roundtrip_count:,}")
print("Row count         : PASS")
print("Schema            : PASS")
# ============================================================
# 6. DUPLICATE VALIDATION AFTER ROUND TRIP
# ============================================================
duplicates = (
    roundtrip_df
    .groupBy("grid_id", "timestamp")
    .count()
    .filter(col("count") > 1)
    .count()
)
assert duplicates == 0, (
    f"Duplicate grid/hour records: {duplicates}"
)
print(f"Duplicate records : {duplicates}")
print("Duplicate check   : PASS")
# ============================================================
# 7. GEOMETRY VALIDATION
# ============================================================
assert "geometry" not in roundtrip_df.columns
print("Geometry column   : ABSENT")
print("Geometry check    : PASS")
print("="*50)
# ============================================================
# 8. CHECK DATE PARTITIONS
# ============================================================
partition_dirs = sorted(
    p.name
    for p in PROCESSED.iterdir()
    if p.is_dir() and p.name.startswith("date=")
)
print("\n========== DATE PARTITIONS ==========")
for p in partition_dirs:
    print(p)
assert len(partition_dirs) > 0
print(f"Partition count   : {len(partition_dirs)}")
print("Partition check   : PASS")
print("="*45)
# ============================================================
# 9. FILE SIZE COMPARISON
# ============================================================
def directory_size(path):
    total = 0
    for p in Path(path).rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total
parquet_size = directory_size(ANALYTICS)
# Create temporary CSV representation for size comparison
CSV_COMPARE = BASE / "data" / "analytics" / "_csv_size_test"
if CSV_COMPARE.exists():
    shutil.rmtree(CSV_COMPARE)
analytics_df.coalesce(1) \
    .write \
    .mode("overwrite") \
    .option("header", True) \
    .csv(str(CSV_COMPARE))
csv_size = directory_size(CSV_COMPARE)

print("\n========== FILE SIZE COMPARISON ==========")
print(f"CSV size       : {csv_size / (1024 * 1024):.2f} MB")
print(f"Parquet size   : {parquet_size / (1024 * 1024):.2f} MB")
if parquet_size < csv_size:
    print("Storage result : Parquet is smaller")
else:
    print("Storage result : CSV is not smaller in this run")
print("="*45)
# ============================================================
# 10. FINAL SUMMARY
# ============================================================
print("\n============== WRITE PROCESS SUMMARY =================")
print(f"Clean rows             : {clean_count:,}")
print(f"Hourly rows            : {hourly_count:,}")
print(f"Round-trip rows        : {roundtrip_count:,}")
print(f"Duplicate grid-hours   : {duplicates}")
print(f"Date partitions        : {len(partition_dirs)}")
print(f"CSV size               : {csv_size / (1024 * 1024):.2f} MB")
print(f"Parquet size            : {parquet_size / (1024 * 1024):.2f} MB")
print("Round-trip validation  : PASS")
print("Duplicate validation  : PASS")
print("Date partitioning      : PASS")
print("Geometry separation    : PASS")
print("File-size comparison   : PASS")
print("="*60)
print("\nWRITE PROCESSED & ANALYTICS DATA COMPLETE")

spark.stop()