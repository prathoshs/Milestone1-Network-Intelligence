# import os
# import json
# from pathlib import Path
# from pyspark import StorageLevel
# os.environ["HADOOP_HOME"] = (
#     r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
# )
# os.environ["PATH"] += (
#     r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
# )
# from pyspark.sql import SparkSession
# from pyspark.sql.functions import (
#     col, broadcast, sum, desc, countDistinct,
#     first, expr
# )
# # ============================================================
# # CONFIG
# # ============================================================
# BASE = Path(__file__).resolve().parent
# ACTIVITY_INPUT = BASE / "output" / "hourly_grid_summary"
# GEOJSON = BASE.parent / "dataset" / "milano-grid.geojson"
# OUT = BASE / "output"
# OUT.mkdir(exist_ok=True)
# # ============================================================
# # SPARK
# # ============================================================
# spark = (
#     SparkSession.builder
#     .appName("NetworkProject-SP4")
#     .master("local[*]")
#     .getOrCreate()
# )
# spark.sparkContext.setLogLevel("WARN")
# # ============================================================
# # READ SP3 ACTIVITY DATA
# # ============================================================
# network_df = spark.read.parquet(
#     str(ACTIVITY_INPUT)
# )
# network_count = network_df.count()
# activity_grids = network_df.select(
#     "grid_id"
# ).distinct().count()
# print("\n=============== INPUT ===================")
# print(f"Activity rows       : {network_count:,}")
# print(f"Distinct grids      : {activity_grids:,}")
# print("="*45)
# # ============================================================
# # READ GEOJSON
# # ============================================================
# with open(GEOJSON, "r", encoding="utf-8") as f:
#     geo = json.load(f)
# print("\n============== GEOJSON =====================")
# print(f"Top-level type      : {geo.get('type')}")
# print(f"Feature count       : {len(geo.get('features', []))}")
# print("="*45)
# # ============================================================
# # BUILD GRID LOOKUP
# # IMPORTANT: properties.cellId → grid_id
# # DO NOT USE feature["id"] — it is 0-based.
# # ============================================================
# features = []

# for feature in geo["features"]:
#     properties = feature.get("properties", {})
#     geometry = feature.get("geometry")
#     # REQUIRED JOIN KEY:
#     # GeoJSON properties.cellId maps to project grid_id.
#     grid_id = properties.get("cellId")
#     if grid_id is not None and geometry is not None:
#         features.append(
#             (
#                 int(grid_id),
#                 json.dumps(geometry)
#             )
#         )
# grid_lookup = spark.createDataFrame(
#     features,
#     ["grid_id", "geometry"]
# )
# lookup_count = grid_lookup.count()
# lookup_duplicates = (
#     grid_lookup
#     .groupBy("grid_id")
#     .count()
#     .filter(col("count") > 1)
#     .count()
# )
# print(f"Grid lookup rows    : {lookup_count:,}")
# print(f"Lookup duplicates   : {lookup_duplicates}")
# assert lookup_count == 10000
# assert lookup_duplicates == 0
# # ============================================================
# # STANDARD JOIN PLAN
# # ============================================================
# print("\n=============== STANDARD JOIN PLAN ================")
# standard_join = network_df.join(
#     grid_lookup,
#     "grid_id",
#     "left"
# )
# standard_join.explain()
# print("="*55)
# # ============================================================
# # BROADCAST JOIN
# # ============================================================
# print("\n============ BROADCAST JOIN PLAN ============")
# grid_activity_geo_df = (
#     network_df
#     .join(
#         broadcast(grid_lookup),
#         "grid_id",
#         "left"
#     )
#     .persist(StorageLevel.DISK_ONLY)
# )
# grid_activity_geo_df.explain()
# print("="*55)
# # ============================================================
# # JOIN VALIDATION
# # ============================================================
# after_count = grid_activity_geo_df.count()
# joined_grids = grid_activity_geo_df.select(
#     "grid_id"
# ).distinct().count()
# missing_geometry = (
#     grid_activity_geo_df
#     .filter(col("geometry").isNull())
#     .select("grid_id")
#     .distinct()
# )
# missing_count = missing_geometry.count()
# coverage = (
#     (activity_grids - missing_count)
#     / activity_grids * 100
# )
# assert joined_grids == activity_grids
# assert missing_count == 0
# assert after_count == network_count
# print("\n================== JOIN VALIDATION ==================")
# print(f"Distinct grids before : {activity_grids:,}")
# print(f"Distinct grids after  : {joined_grids:,}")
# print(f"Missing geometries    : {missing_count:,}")
# print(f"Coverage              : {coverage:.2f}%")
# print(f"Rows before join      : {network_count:,}")
# print(f"Rows after join       : {after_count:,}")
# print("="*60)
# # ============================================================
# # UNMATCHED GRID LIST
# # ============================================================
# unmatched = (
#     network_df
#     .select("grid_id")
#     .distinct()
#     .join(
#         grid_lookup.select("grid_id"),
#         "grid_id",
#         "left_anti"
#     )
# )
# unmatched_count = unmatched.count()
# assert unmatched_count == 0
# print(f"Unmatched grid IDs: {unmatched_count}")
# if unmatched_count > 0:
#     unmatched.coalesce(1).write.mode("overwrite") \
#         .option("header", True) \
#         .csv(str(OUT / "unmatched_grid_ids"))
# # ============================================================
# # GEOGRAPHIC SPOT CHECK
# # ============================================================
# print("\n========== GEOGRAPHIC SPOT CHECK ==========")
# # Show grid 1 and grid 2 geometry.
# # The lookup MUST use properties.cellId.
# grid_lookup.filter(
#     col("grid_id").isin(1, 2)
# ).show(truncate=False)
# # Basic coordinate extraction from Polygon/MultiPolygon GeoJSON.
# # Prints the first coordinate as [longitude, latitude].
# # spot_check = (
# #     grid_lookup
# #     .filter(col("grid_id").isin(1, 2))
# #     .select(
# #         "grid_id",
# #         expr(
# #             "from_json(geometry, "
# #             "'struct<type:string,coordinates:array<array<array<double>>>>')"
# #         ).alias("g")
# #     )
# # )
# # spot_check.select(
# #     "grid_id",
# #     col("g.type").alias("geometry_type"),
# #     col("g.coordinates")[0][0].alias("first_coordinate")
# # ).show(truncate=False)
# for gid in [1, 2]:
#     feature = next(
#         f for f in geo["features"]
#         if int(f["properties"]["cellId"]) == gid
#     )
#     coords = feature["geometry"]["coordinates"]
#     # First polygon ring, first coordinate
#     point = coords[0][0] if feature["geometry"]["type"] == "Polygon" else coords[0][0][0]
#     print(
#         f"Grid {gid}: "
#         f"type={feature['geometry']['type']}, "
#         f"first_coordinate={point}"
#     )
# print("Geographic spot-check: PASS")
# print("="*60)
# # ============================================================
# # TOP HIGH-ACTIVITY GRIDS WITH GEOMETRY
# # ============================================================
# top_grids = (
#     grid_activity_geo_df
#     .groupBy("grid_id")
#     .agg(
#         sum("total_activity").alias("total_activity"),
#         first("geometry").alias("geometry")
#     )
#     .orderBy(desc("total_activity"))
#     .limit(10)
# )
# top_grids.write.mode("overwrite").option(
#     "header", True
# ).csv(str(OUT / "top_activity_grids_geo"))
# # ============================================================
# # FINAL ENRICHED DATASET
# # ============================================================
# grid_activity_geo_df = grid_activity_geo_df.select(
#     "timestamp",
#     "grid_id",
#     "sms_in",
#     "sms_out",
#     "call_in",
#     "call_out",
#     "internet_activity",
#     "total_activity",
#     "geometry"
# )
# grid_activity_geo_df.write.mode(
#     "overwrite"
# ).parquet(
#     str(OUT / "grid_activity_geo")
# )
# # ============================================================
# # FINAL SUMMARY
# # ============================================================
# print("\n============ GEOSPATIAL ENRICHMENT SUMMARY ============")
# print(f"Activity rows          : {network_count:,}")
# print(f"Grid lookup rows       : {lookup_count:,}")
# print(f"Distinct grids         : {activity_grids:,}")
# print(f"Missing grids          : {unmatched_count:,}")
# print(f"Missing geometry       : {missing_count:,}")
# print(f"Enrichment coverage    : {coverage:.2f}%")
# print(f"Rows before join       : {network_count:,}")
# print(f"Rows after join        : {after_count:,}")
# print("Join row-count check   : PASS")
# print("Coverage check         : PASS")
# print("Unmatched-grid check   : PASS")
# print("GeoJSON key            : properties.cellId")
# print("Country-code column    : NOT USED")
# print("="*60)
# print("GEOSPATIAL ENRICHMENT COMPLETE")

# spark.stop()





import os
import json
from pathlib import Path
os.environ["HADOOP_HOME"] = (
    r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
)
os.environ["PATH"] += (
    r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
)
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, broadcast, sum, first, desc
) 
# ============================================================
# CONFIG
# ============================================================
BASE = Path(__file__).resolve().parent
ACTIVITY_INPUT = BASE / "output" / "hourly_grid_summary"
GEOJSON = BASE.parent / "dataset" / "milano-grid.geojson"
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)
# ============================================================
# SPARK
# ============================================================
spark = (
    SparkSession.builder
    .appName("NetworkProject-SP4")
    .master("local[1]")
    .config("spark.sql.shuffle.partitions", "8")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
# ============================================================
# READ SP3 OUTPUT
# ============================================================
network_df = spark.read.parquet(
    str(ACTIVITY_INPUT)
)
network_count = network_df.count()
activity_grids = (
    network_df
    .select("grid_id")
    .distinct()
    .count()
)
print("\n==========  INPUT ==========")
print(f"Activity rows       : {network_count:,}")
print(f"Distinct grids      : {activity_grids:,}")
print("="*45)
# ============================================================
# READ GEOJSON
# ============================================================
with open(GEOJSON, "r", encoding="utf-8") as f:
    geo = json.load(f)
features = geo["features"]
print("\n========== GEOJSON ==========")
print(f"Top-level type      : {geo.get('type')}")
print(f"Feature count       : {len(features):,}")
assert geo.get("type") == "FeatureCollection"
assert len(features) == 10000
# ============================================================
# BUILD LOOKUP
# IMPORTANT:
# properties.cellId → grid_id
# DO NOT USE feature["id"].
# ============================================================
lookup_data = []
for feature in features:
    # REQUIRED PROJECT JOIN KEY:
    # GeoJSON properties.cellId maps to grid_id.
    grid_id = feature["properties"]["cellId"]
    lookup_data.append(
        (
            int(grid_id),
            json.dumps(feature["geometry"])
        )
    )
grid_lookup = spark.createDataFrame(
    lookup_data,
    ["grid_id", "geometry"]
)
lookup_count = grid_lookup.count()
lookup_duplicates = (
    grid_lookup
    .groupBy("grid_id")
    .count()
    .filter(col("count") > 1)
    .count()
)
assert lookup_count == 10000
assert lookup_duplicates == 0
print(f"Grid lookup rows    : {lookup_count:,}")
print(f"Lookup duplicates   : {lookup_duplicates}")
print("="*45)
# ============================================================
# STANDARD JOIN PLAN
# ============================================================
print("\n================================ STANDARD JOIN PLAN ======================================================")
network_df.join(
    grid_lookup,
    "grid_id",
    "left"
).explain()
print("="*120)
# ============================================================
# BROADCAST JOIN
# ============================================================
print("\n================================= BROADCAST JOIN PLAN ======================================================")
grid_activity_geo_df = (
    network_df
    .join(
        broadcast(grid_lookup),
        "grid_id",
        "left"
    )
)
grid_activity_geo_df.explain()
print("="*120)
# ============================================================
# JOIN VALIDATION
# ============================================================
after_count = grid_activity_geo_df.count()
joined_grids = (
    grid_activity_geo_df
    .select("grid_id")
    .distinct()
    .count()
)
missing_geometry = (
    grid_activity_geo_df
    .filter(col("geometry").isNull())
    .select("grid_id")
    .distinct()
)
missing_count = missing_geometry.count()
coverage = (
    (activity_grids - missing_count)
    / activity_grids * 100
)
assert joined_grids == activity_grids
assert missing_count == 0
assert after_count == network_count
print("\n========== JOIN VALIDATION ==========")
print(f"Distinct grids before : {activity_grids:,}")
print(f"Distinct grids after  : {joined_grids:,}")
print(f"Missing geometries    : {missing_count:,}")
print(f"Coverage              : {coverage:.2f}%")
print(f"Rows before join      : {network_count:,}")
print(f"Rows after join       : {after_count:,}")
print("="*45)
# ============================================================
# UNMATCHED GRID LIST
# ============================================================
unmatched = (
    network_df
    .select("grid_id")
    .distinct()
    .join(
        grid_lookup.select("grid_id"),
        "grid_id",
        "left_anti"
    )
)
unmatched_count = unmatched.count()
assert unmatched_count == 0
print(f"Unmatched grid IDs   : {unmatched_count}")
# Only write if something is actually unmatched
if unmatched_count > 0:
    unmatched.coalesce(1).write.mode(
        "overwrite"
    ).option(
        "header", True
    ).csv(
        str(OUT / "unmatched_grid_ids")
    )
# ============================================================
# GEOGRAPHIC SPOT CHECK
# PYTHON ONLY — NO SPARK ACTION
# ============================================================
print("\n=============== GEOGRAPHIC SPOT CHECK ====================")
geo_by_id = {
    int(f["properties"]["cellId"]): f
    for f in features
}
assert 1 in geo_by_id
assert 2 in geo_by_id
def polygon_centroid(feature):
    geometry = feature["geometry"]
    if geometry["type"] == "Polygon":
        ring = geometry["coordinates"][0]
    elif geometry["type"] == "MultiPolygon":
        ring = geometry["coordinates"][0][0]
    else:
        raise ValueError(
            f"Unsupported geometry: {geometry['type']}"
        )
    # Simple polygon centroid approximation
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (
        __builtins__.sum(xs) / len(xs),
        __builtins__.sum(ys) / len(ys)
    )
centroid_1 = polygon_centroid(geo_by_id[1])
centroid_2 = polygon_centroid(geo_by_id[2])
print(
    f"Grid 1 centroid : "
    f"longitude={centroid_1[0]:.6f}, "
    f"latitude={centroid_1[1]:.6f}"
)
print(
    f"Grid 2 centroid : "
    f"longitude={centroid_2[0]:.6f}, "
    f"latitude={centroid_2[1]:.6f}"
)
distance = (
    (centroid_1[0] - centroid_2[0]) ** 2
    + (centroid_1[1] - centroid_2[1]) ** 2
) ** 0.5
assert distance > 0
assert distance < 1
print(f"Grid 1-2 centroid distance : {distance:.6f}")
print("Grid 1 and Grid 2 are adjacent/non-identical")
print("Geographic spot-check       : PASS")
print("="*50)
# ============================================================
# TOP HIGH-ACTIVITY GRIDS
# ============================================================
top_grids = (
    grid_activity_geo_df
    .groupBy("grid_id")
    .agg(
        sum("total_activity").alias("total_activity"),
        first("geometry").alias("geometry")
    )
    .orderBy(desc("total_activity"))
    .limit(10)
)
top_grids.coalesce(1).write.mode(
    "overwrite"
).option(
    "header", True
).csv(
    str(OUT / "top_activity_grids_geo")
)
# ============================================================
# FINAL ENRICHED DATASET
# ============================================================
grid_activity_geo_df = grid_activity_geo_df.select(
    "grid_id",
    "timestamp",
    "sms_in",
    "sms_out",
    "call_in",
    "call_out",
    "internet_activity",
    "total_activity",
    "geometry"
)
grid_activity_geo_df.write.mode(
    "overwrite"
).parquet(
    str(OUT / "grid_activity_geo")
)
# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n========== GEOSPATIAL ENRICHMENT SUMMARY ==========")
print(f"Activity rows          : {network_count:,}")
print(f"Grid lookup rows       : {lookup_count:,}")
print(f"Distinct grids         : {activity_grids:,}")
print(f"Missing grids          : {unmatched_count:,}")
print(f"Missing geometry       : {missing_count:,}")
print(f"Enrichment coverage    : {coverage:.2f}%")
print(f"Rows before join       : {network_count:,}")
print(f"Rows after join        : {after_count:,}")

print("Join row-count check   : PASS")
print("Coverage check         : PASS")
print("Unmatched-grid check   : PASS")
print("Geographic check       : PASS")
print("GeoJSON key            : properties.cellId")
print("="*60)
print("GEOSPATIAL ENRICHMENT COMPLETE")

spark.stop()