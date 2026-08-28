import os
from pathlib import Path
# from pyspark.sql.types import (
#     StructType, StructField, TimestampType,
#     StringType, DoubleType
# )
# ============================================================
# WINDOWS HADOOP
# ============================================================
os.environ["HADOOP_HOME"] = (
    r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
)
os.environ["PATH"] += (
    r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
)
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, input_file_name, to_timestamp, to_date,
    hour, dayofweek, when, lit, countDistinct,
    sum as Fsum, date_trunc
)
# ============================================================
# CONFIGURATION
# ============================================================
BASE = Path(__file__).resolve().parent
# DATA_FOLDER = BASE.parent / "dataset"
# FILE_PATTERN = str(DATA_FOLDER / "sms-call-internet-mi-*.csv")
PARQUET_PATH = (
    BASE / "parquet_output" / "raw_parquet"
)

OUT = BASE / "output"
OUT.mkdir(exist_ok=True)
mapping = {
    "datetime": "timestamp",
    "CellID": "grid_id",
    "countrycode": "country_code",
    "smsin": "sms_in",
    "smsout": "sms_out",
    "callin": "call_in",
    "callout": "call_out",
    "internet": "internet_activity"
}
activity = [
    "sms_in",
    "sms_out",
    "call_in",
    "call_out",
    "internet_activity"
]
# ============================================================
# SPARK
# ============================================================
spark = (
    SparkSession.builder
    .appName("NetworkProject")
    .master("local[1]")
    .config("spark.sql.shuffle.partitions", "4")
    .config("spark.driver.memory", "4g")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
# ============================================================
# READ ALL 7 DAILY FILES
# ============================================================
# files = sorted(glob.glob(FILE_PATTERN))
# if not files:
#     raise FileNotFoundError(
#         f"No files found: {FILE_PATTERN}"
#     )
# print(f"\nFiles found: {len(files)}")
# schema = StructType([
#     StructField("datetime", TimestampType(), True),
#     StructField("CellID", StringType(), True),
#     StructField("countrycode", StringType(), True),
#     StructField("smsin", DoubleType(), True),
#     StructField("smsout", DoubleType(), True),
#     StructField("callin", DoubleType(), True),
#     StructField("callout", DoubleType(), True),
#     StructField("internet", DoubleType(), True)
# ])
# raw_network_df = (
#     spark.read
#     .option("header", True)
#     .option("inferSchema", False)
#     .csv(files)
#     .withColumn("input_file_name", input_file_name())
# )
# raw_count = raw_network_df.count()
# ============================================================
# READ SP1 PARQUET OUTPUT
# ============================================================
print("\nReading Parquet output:")
print(PARQUET_PATH)
raw_network_df = spark.read.parquet(
    str(PARQUET_PATH)
)
raw_count = raw_network_df.count()
print(f"Raw rows: {raw_count:,}")
# ============================================================
# RENAME TO CANONICAL NAMES
# ============================================================
for old, new in mapping.items():
    raw_network_df = raw_network_df.withColumnRenamed(
        old, new
    )
clean_network_df = raw_network_df
# ============================================================
# PROFILE ACTIVITY NULLS BEFORE ZERO FILL
# ============================================================
null_expr = [
    Fsum(
        when(col(c).isNull(), 1).otherwise(0)
    ).alias(c)
    for c in activity
]
null_row = clean_network_df.agg(
    *null_expr
).first()
null_counts = {
    c: int(null_row[c] or 0)
    for c in activity
}
null_handled = sum(null_counts.values())
# ============================================================
# IDENTIFY BAD RECORDS
# ============================================================
bad = (
    col("grid_id").isNull()
    | (col("grid_id") == "")
    | col("timestamp").isNull()
)
for c in activity:
    bad = bad | (
        col(c).isNotNull() & (col(c) < 0)
    )
rejected_count = (
    clean_network_df
    .filter(bad)
    .count()
)
# Keep only valid records
clean_network_df = clean_network_df.filter(~bad | bad.isNull())
clean_count = clean_network_df.count()

print("RAW:", raw_count)
print("REJECTED:", rejected_count)
print("CLEAN:", clean_count)
assert clean_count == raw_count - rejected_count
# ============================================================
# VALIDATE RECORD COUNTS
# ============================================================
if clean_count != raw_count - rejected_count:
    raise ValueError(
        "Record count validation failed: "
        f"RAW={raw_count}, "
        f"REJECTED={rejected_count}, "
        f"CLEAN={clean_count}"
    )
# ============================================================
# CURATED NULL → ZERO
# ============================================================
for c in activity:
    clean_network_df = clean_network_df.withColumn(
        c,
        when(col(c).isNull(), lit(0.0))
        .otherwise(col(c))
    )
# ============================================================
# DERIVED FEATURES
# ============================================================
clean_network_df = (
    clean_network_df
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
    .withColumn(
        "date",
        to_date("timestamp")
    )
    .withColumn(
        "hour",
        hour("timestamp")
    )
    .withColumn(
        "day_of_week",
        dayofweek("timestamp")
    )
    .withColumn(
        "hour_timestamp",
        date_trunc("hour", "timestamp")
    )
)
# ============================================================
# HOURLY CADENCE CHECK
# ============================================================
cadence = clean_network_df.agg(
    countDistinct("date").alias("days"),
    countDistinct("hour_timestamp").alias("hours")
).first()
days = cadence["days"]
hours = cadence["hours"]
expected = days * 24
if hours != expected:
    raise ValueError(
        f"Hourly cadence failed: "
        f"{hours} != {expected}"
    )
# ============================================================
# FINAL DATA VALIDATION
# ============================================================
if clean_network_df.filter(
    col("grid_id").isNull() |
    (col("grid_id") == "")
).count() != 0:
    raise ValueError("Invalid grid_id remains.")
if clean_network_df.filter(
    col("timestamp").isNull()
).count() != 0:
    raise ValueError("Invalid timestamp remains.")
# ============================================================
# REPORT 1 — NULL HANDLING
# ============================================================
spark.createDataFrame(
    [(c, null_counts[c]) for c in activity],
    ["activity_column", "nulls_converted_to_zero"]
).coalesce(1).write.mode(
    "overwrite"
).option(
    "header", True
).csv(
    str(OUT / "null_handling_report")
)
# ============================================================
# REPORT 2 — REJECTED RECORDS
# ============================================================
spark.createDataFrame(
    [
        ("RAW", raw_count),
        ("REJECTED", rejected_count),
        ("CLEAN", clean_count)
    ],
    ["record_type", "row_count"]
).coalesce(1).write.mode(
    "overwrite"
).option(
    "header", True
).csv(
    str(OUT / "rejected_record_summary")
)
# ============================================================
# 20. COUNT CLEAN ROWS
# ============================================================
clean_count = clean_network_df.count()
# ============================================================
# 21. VERIFY ROW COUNT BALANCE
# Before = Valid + Rejected
# ============================================================
print("\n========== ROW COUNT CHECK ==========")
print(
    "Rows before cleaning:",
    raw_count
)
print(
    "Rows rejected:",
    rejected_count
)
print(
    "Rows after cleaning:",
    clean_count
)
print(
    "Rejected + Clean:",
    rejected_count + clean_count
)
assert raw_count == (
    rejected_count + clean_count
), "Row count mismatch!"

print("Row count check: PASS")

# ============================================================
# 23. INSPECT FINAL CLEAN DATA
# ============================================================
 
print("\n========== FINAL CLEAN SCHEMA ==========")
 
clean_network_df.printSchema()
 
 
print("\n========== FINAL CLEAN DATA ==========")
clean_network_df.show(
    10,
    truncate=False
)
# ============================================================
# FINAL OUTPUT
# ============================================================
print("\n========== CLEANING AND STANDARDIZATIONSUMMARY ==========")
# print(f"Files found       : {len(files)}")
print(f"Raw rows          : {raw_count:,}")
print(f"Rejected rows     : {rejected_count:,}")
print(f"Clean rows        : {clean_count:,}")
print(f"Nulls handled     : {null_handled:,}")
print(f"Days              : {days}")
print(f"Hourly intervals  : {hours}")
print(f"Expected D×24     : {expected}")
print("Record count      : PASS")
print("Hourly cadence    : PASS")
print("="*70)
print("CLEANING AND STANDARDIZATION COMPLETE")

clean_network_df \
    .repartition(4, "date") \
    .write \
    .mode("overwrite") \
    .partitionBy("date") \
    .parquet(str(OUT / "clean_network"))

spark.stop()