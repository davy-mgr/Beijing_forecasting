-- Task 2: SQL queries (PostgreSQL). Run in psql and paste the output into the report.

-- Q1. Monthly average PM2.5 and temperature, plus how many hours are missing
SELECT date_trunc('month', ts)::date          AS month,
       ROUND(AVG(pm25), 1)                    AS avg_pm25,
       ROUND(AVG(temp), 1)                    AS avg_temp_c,
       COUNT(*) FILTER (WHERE pm25 IS NULL)   AS missing_pm25_hours
FROM v_hourly_observations
GROUP BY 1
ORDER BY 1;

-- Q2. Average PM2.5 by wind direction (3-table join)
SELECT wd.code                    AS wind_dir,
       wd.description,
       ROUND(AVG(a.pm25), 1)      AS avg_pm25,
       COUNT(a.pm25)              AS n_readings
FROM air_quality_readings a
JOIN weather_readings w  ON w.ts = a.ts
JOIN wind_directions wd  ON wd.wind_dir_id = w.wind_dir_id
GROUP BY wd.code, wd.description
ORDER BY avg_pm25 DESC;

-- Q3. Hours above 150 ug/m^3 per year (share of non-missing hours)
SELECT EXTRACT(YEAR FROM ts)::int                           AS year,
       COUNT(*) FILTER (WHERE pm25 > 150)                   AS hours_above_150,
       COUNT(pm25)                                          AS valid_hours,
       ROUND(100.0 * COUNT(*) FILTER (WHERE pm25 > 150)
             / NULLIF(COUNT(pm25), 0), 1)                   AS pct_above_150
FROM air_quality_readings
GROUP BY 1
ORDER BY 1;

-- Q4. Lag-24 and 24-hour moving average using window functions (links to Task 1B)
SELECT ts,
       pm25,
       LAG(pm25, 24) OVER (ORDER BY ts)                                   AS pm25_lag_24h,
       ROUND(AVG(pm25) OVER (ORDER BY ts
             ROWS BETWEEN 23 PRECEDING AND CURRENT ROW), 1)               AS pm25_ma_24h
FROM air_quality_readings
ORDER BY ts
LIMIT 72;

-- Q5. Latest record (this is the logic the Task 3 endpoint will use)
SELECT * FROM v_hourly_observations ORDER BY ts DESC LIMIT 1;
