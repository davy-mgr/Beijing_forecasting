# Task 3 — CRUD and Time-Series API

Task 3 uses the same databases and schema established in Task 2.

- PostgreSQL database: `beijing_air`
- SQL tables: `stations`, `wind_directions`, `air_quality_readings`, `weather_readings`
- SQL time-series view: `v_hourly_observations`
- MongoDB database/collection: `beijing_air.readings`

## Start databases
From the repository root run:
```bash
cd Task2
docker compose up -d
```
PostgreSQL is exposed on host port `5433` (container port `5432`) to match `Task3/sql_endpoints.py`; MongoDB uses port `27017`.

## Start API
In another terminal run:
```bash
cd Task3
python -m pip install -r requirements.txt
uvicorn api:app --reload
```
Open `http://127.0.0.1:8000/docs`.

## SQL time-series queries
- `GET /sql/readings/latest` — latest joined observation from `v_hourly_observations`.
- `GET /sql/readings?start=2014-01-01T00:00:00&end=2014-01-02T00:00:00` — date range, start inclusive/end exclusive.

## SQL air-quality CRUD
- `POST /sql/air-quality`
- `GET /sql/air-quality`
- `GET /sql/air-quality/{reading_id}`
- `PUT /sql/air-quality/{reading_id}`
- `DELETE /sql/air-quality/{reading_id}`

Example body: `{"station_id":1,"ts":"2014-01-01T00:00:00","pm25":80}`

## SQL weather CRUD
- `POST /sql/weather`
- `GET /sql/weather`
- `GET /sql/weather/{reading_id}`
- `PUT /sql/weather/{reading_id}`
- `DELETE /sql/weather/{reading_id}`

## MongoDB CRUD and time-series queries
- `GET /mongo/readings/latest` — latest document.
- `GET /mongo/readings` — list documents (supports `limit` and `skip`).
- `GET /mongo/readings?start=2014-01-01T00:00:00&end=2014-01-02T00:00:00` — date-range query.
- `POST /mongo/readings` — create document.
- `GET /mongo/readings/{timestamp}` — get by exact timestamp.
- `PUT /mongo/readings/{timestamp}` — replace document; body timestamp must match URL.
- `DELETE /mongo/readings/{timestamp}` — delete by exact timestamp.

Example MongoDB body:
```json
{
  "timestamp":"2014-01-01T00:00:00",
  "air_quality":{"station":"US Embassy Beijing","pm25":80},
  "weather":{"station":"Beijing Capital International Airport","dewp":-5.0,"temp":-2.0,"pres":1020.0,"wind":{"direction":"NE","cum_speed":1.2},"snow_hours":0,"rain_hours":0}
}
```
The API can derive `calendar` from `timestamp` when omitted.

## Test notes
- Use existing SQL `reading_id` values for PUT/DELETE and an exact existing MongoDB timestamp for GET/PUT/DELETE.
- SQL station and wind direction IDs must exist in Task 2's lookup tables.
- Duplicate SQL `(station_id, ts)` or duplicate MongoDB timestamps return HTTP 409; missing records return 404.
