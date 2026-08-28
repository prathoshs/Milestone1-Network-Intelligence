import os
import glob
 
os.environ["HADOOP_HOME"] = r"C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6"
os.environ["PATH"] += r";C:\Users\prathosh.s\Videos\pysparkexer\winutils\hadoop-3.3.6\bin"
from pyspark.sql import SparkSession
 
from pyspark.sql.types import (
    StructType,
    StructField,
    TimestampType,
    IntegerType,
    StringType,
    DoubleType
)
from pyspark.sql.functions import input_file_name,date_trunc
 
spark = (
    SparkSession.builder
    .appName("NetworkProject1")
    # .master("local[*]")
    .getOrCreate()
)
 
 
DATA_FOLDER = "D:/Milestone1proj/dataset"
 
FILE_PATTERN = os.path.join(
    DATA_FOLDER,
    "sms-call-internet-mi-*.csv"
)
 

# df = (
#     spark.read
#     .option("header", True)
#     .option("inferSchema", True)
#     .csv(input_path)
# )
 
actual_files = glob.glob(FILE_PATTERN)
 
print("\nFiles found:")
for file in actual_files:
    print(os.path.basename(file))
print("\nActual file count:", len(actual_files))
 
schema = StructType([
    StructField("datetime", TimestampType(), True),
    StructField("CellID", StringType(), True),
    StructField("countrycode", StringType(), True),
    StructField("smsin", DoubleType(), True),
    StructField("smsout", DoubleType(), True),
    StructField("callin", DoubleType(), True),
    StructField("callout", DoubleType(), True),
    StructField("internet", DoubleType(), True)
])
 
df = (
    spark.read
    .option("header", True)
    .schema(schema)
    .csv(FILE_PATTERN)
)
print("csv read with struct feilds.....")
 
row_count = df.count()
print("Total rows:", row_count)
 
df = df.withColumn(
    "source_file",
    input_file_name()
)
 
source_file_count = df.select("source_file").distinct().count()
print("Source files:", source_file_count)
 
df.select("source_file").distinct().show(truncate=False)
 
unique_grids = df.select("CellID").distinct().count()
print("Unique grids:", unique_grids)
  
country_codes = df.select("countrycode").distinct().count()
print("Country-code categories:", country_codes)
 
#df.select("countrycode").distinct().show()

hourly_intervals = (
    df.select("datetime")
      .distinct()
      .count()
) 
print("Distinct hourly intervals:", hourly_intervals)
 
df.select("datetime").distinct().orderBy("datetime").show(
    10,
    truncate=False
)

df = df.withColumn(
    "hour",
    date_trunc("hour", "datetime")
)
 
hourly_intervals = df.select("hour").distinct().count()

print("Final hourly intervals:", hourly_intervals)

df.write.mode("overwrite").parquet(
    r"parquet_output\raw_parquet"
)

print("Parquet file written successfully.")