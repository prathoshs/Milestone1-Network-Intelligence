# Storage Strategy & Data Zones

## 1. Purpose

This storage contract defines how telecom data is organized,
stored, written, partitioned and retained across the platform.

## 2. Storage Zones

### landing/

- Format: CSV
- Write mode: Append / new files
- Retention: Short-term

### raw/

- Format: CSV
- Write mode: Append only
- Retention: Long-term
- Immutability: Required

Raw data is retained unchanged for auditability, traceability,
reprocessing and replay.

### reference/

- Format: GeoJSON
- Write mode: Controlled versioned replacement
- Partitioning: Not date-partitioned
- Retention: Long-term

The reference zone is static or slowly changing and therefore is
not partitioned by event date.

### processed/

- Format: Parquet
- Write mode: Append by date partition
- Partition key: date=YYYY-MM-DD
- Retention: Medium to long-term

### analytics/

- Format: Parquet / warehouse tables
- Write mode: Overwrite affected partitions or tables
- Partitioning: Based on query workload
- Retention: Medium-term

### logs/

- Format: Text / CSV
- Write mode: Append
- Partitioning: Optional date-based organization
- Retention: Operational retention period
