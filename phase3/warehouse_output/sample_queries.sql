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
