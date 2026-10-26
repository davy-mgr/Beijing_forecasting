-- Beijing PM2.5 (UCI #381) - PostgreSQL schema
-- Design choice: the database stores RAW values (missing PM2.5 stays NULL).
-- Imputation happens in the preprocessing pipeline, not in storage.

DROP VIEW  IF EXISTS v_hourly_observations;
DROP TABLE IF EXISTS weather_readings;
DROP TABLE IF EXISTS air_quality_readings;
DROP TABLE IF EXISTS wind_directions;
DROP TABLE IF EXISTS stations;

CREATE TABLE stations (
    station_id   SERIAL PRIMARY KEY,
    name         VARCHAR(100) NOT NULL UNIQUE,
    station_type VARCHAR(20)  NOT NULL
                 CHECK (station_type IN ('air_quality', 'meteorological')),
    city         VARCHAR(50)  NOT NULL
);

CREATE TABLE wind_directions (
    wind_dir_id SERIAL PRIMARY KEY,
    code        VARCHAR(4)  NOT NULL UNIQUE,
    description VARCHAR(60) NOT NULL
);

CREATE TABLE air_quality_readings (
    reading_id BIGSERIAL PRIMARY KEY,
    station_id INT       NOT NULL REFERENCES stations(station_id),
    ts         TIMESTAMP NOT NULL,              -- local Beijing time, hourly
    pm25       INT       CHECK (pm25 >= 0),     -- ug/m^3, NULL = missing
    UNIQUE (station_id, ts)
);

CREATE TABLE weather_readings (
    reading_id     BIGSERIAL PRIMARY KEY,
    station_id     INT       NOT NULL REFERENCES stations(station_id),
    ts             TIMESTAMP NOT NULL,
    dewp           NUMERIC(5,1),                -- dew point, deg C
    temp           NUMERIC(5,1),                -- temperature, deg C
    pres           NUMERIC(6,1),                -- pressure, hPa
    wind_dir_id    INT REFERENCES wind_directions(wind_dir_id),
    cum_wind_speed NUMERIC(7,2),                -- cumulated wind speed, m/s
    cum_snow_hours INT,                         -- cumulated hours of snow
    cum_rain_hours INT,                         -- cumulated hours of rain
    UNIQUE (station_id, ts)
);

CREATE INDEX idx_aq_ts ON air_quality_readings (ts);
CREATE INDEX idx_wx_ts ON weather_readings (ts);

-- Lookup / reference data
INSERT INTO stations (name, station_type, city) VALUES
    ('US Embassy Beijing', 'air_quality', 'Beijing'),
    ('Beijing Capital International Airport', 'meteorological', 'Beijing');

INSERT INTO wind_directions (code, description) VALUES
    ('NE', 'North-east'),
    ('NW', 'North-west'),
    ('SE', 'South-east'),
    ('cv', 'Calm and variable');

-- Convenience view: one row per hour with pollution + weather together
CREATE VIEW v_hourly_observations AS
SELECT a.ts,
       a.pm25,
       w.dewp,
       w.temp,
       w.pres,
       wd.code AS wind_dir,
       w.cum_wind_speed,
       w.cum_snow_hours,
       w.cum_rain_hours
FROM air_quality_readings a
JOIN weather_readings w         ON w.ts = a.ts
LEFT JOIN wind_directions wd    ON wd.wind_dir_id = w.wind_dir_id;
