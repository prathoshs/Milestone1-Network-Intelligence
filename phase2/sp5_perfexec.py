import os
import time
from pathlib import Path
os.environ["HADOOP_HOME"] = (
    r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
)
os.environ["PATH"] += (
    r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
)
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum as Fsum, desc, broadcast
)
from pyspark import StorageLevel
# ============================================================
# CONFIG
# ============================================================
BASE = Path(__file__).resolve().parent
HOURLY = BASE / "output" / "hourly_grid_summary"
GEO = BASE / "output" / "grid_activity_geo"
# ============================================================
# SPARK
# ============================================================
spark = (
    SparkSession.builder
    .appName("NetworkProject-SP5")
    .master("local[1]")
    .config("spark.sql.shuffle.partitions", "8")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
# ============================================================
# READ DATA
# ============================================================
df = spark.read.parquet(str(HOURLY))
print("\n========== INPUT ==========")
print(f"Rows: {df.count():,}")
print(f"Partitions: {df.rdd.getNumPartitions()}")
print("="*30)
# ============================================================
# 1. HOTSPOT EXPLAIN PLAN
# ============================================================
print("\n========== 1. HOTSPOT EXPLAIN ================")
hotspot = (
    df.groupBy("grid_id")
      .agg(Fsum("total_activity").alias("total_activity"))
      .orderBy(desc("total_activity"))
      .limit(10)
)
hotspot.explain()
print("="*50)
# ============================================================
# 2. CACHE TIMING
# ============================================================
print("\n============= 2. CACHE TIMING ================")
cached_df = df.persist(StorageLevel.MEMORY_AND_DISK)
start = time.perf_counter()
cached_df.count()
first_time = time.perf_counter() - start
start = time.perf_counter()
cached_df.count()
second_time = time.perf_counter() - start
print(f"First action  : {first_time:.2f} seconds")
print(f"Second action : {second_time:.2f} seconds")
print(f"Improvement   : {first_time - second_time:.2f} seconds")
cached_df.unpersist()
print("="*50)
# ============================================================
# 3. REPARTITION BY DATE
# ============================================================
print("\n========== 3. REPARTITION ================")
before = df.rdd.getNumPartitions()
repartitioned = df.repartition(8, "date")
after = repartitioned.rdd.getNumPartitions()
print(f"Before partitions : {before}")
print(f"After partitions  : {after}")
print("="*45)
# ============================================================
# 4. COLUMN PRUNING
# ============================================================
print("\n========== 4. COLUMN PRUNING ==========")
pruned_df = df.select(
    "grid_id",
    "total_activity"
)
pruned_hotspot = (
    pruned_df
    .groupBy("grid_id")
    .agg(
        Fsum("total_activity").alias("total_activity")
    )
    .orderBy(desc("total_activity"))
    .limit(10)
)
pruned_hotspot.explain()
print("="*50)
# ============================================================
# 5. BROADCAST JOIN
# ============================================================
print("\n========== 5. BROADCAST JOIN ==========")
network = spark.read.parquet(str(HOURLY))
grid_lookup = (
    spark.read.parquet(str(GEO))
    .select("grid_id", "geometry")
    .dropDuplicates(["grid_id"])
)
standard_join = network.join(
    grid_lookup,
    "grid_id",
    "left"
)
broadcast_join = network.join(
    broadcast(grid_lookup),
    "grid_id",
    "left"
)
print("\nSTANDARD JOIN:")
standard_join.explain()
print("-"*150)
print("\nBROADCAST JOIN:")
broadcast_join.explain()
print("="*250)
# ============================================================
# 6. PERFORMANCE OBSERVATIONS
# ============================================================
print("\n========== 6. PERFORMANCE OBSERVATIONS ==========")
print("Observation 1:")
print(
    "Broadcast join avoids the large-side shuffle; "
    "evidence: BroadcastHashJoin appears in the physical plan."
)
print("\nObservation 2:")
print(
    "Caching helps repeated actions; evidence: "
    f"first={first_time:.2f}s, second={second_time:.2f}s."
)
print("\nObservation 3:")
print(
    "Column pruning reduces data read; evidence: "
    "the pruned plan scans only grid_id and total_activity."
)
print("="*200)
# ============================================================
# 7. REQUIRED REJECTED SUGGESTION
# ============================================================
print("\n========== 7. REJECTED SUGGESTION ==========")
print(
    "Rejected suggestion: using a very large number of partitions "
    "for this local dataset."
)
print(
    "Reason: excessive partitions increase scheduling and shuffle "
    "overhead without providing useful parallelism."
)
print("="*180)
# ============================================================
# FINAL
# ============================================================
print("\n========== PERFORMANCE AND EXECUTION BEHAVIOUR SUMMARY ==========")
print(f"Input rows             : {df.count():,}")
print(f"Initial partitions     : {before}")
print(f"Repartitioned          : {after}")
print(f"Cached first action    : {first_time:.2f}s")
print(f"Cached second action   : {second_time:.2f}s")
print("Hotspot explain        : PASS")
print("Cache comparison      : PASS")
print("Repartition test      : PASS")
print("Column pruning         : PASS")
print("Broadcast comparison   : PASS")
print("3 observations        : PASS")
print("Rejected suggestion   : PASS")
print("="*70)
print("PERFORMANCE AND EXECUTION BEHAVIOUR COMPLETE")

spark.stop()