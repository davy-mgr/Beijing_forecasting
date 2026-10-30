# Beijing PM2.5 Forecasting

A time-series pipeline for hourly PM2.5 air pollution in Beijing: exploratory analysis and a forecasting model, SQL and MongoDB databases, a FastAPI service, and a script that fetches recent data from the API and forecasts the next hour.

## Team

| Member | Task |
|---|---|
| Steven Kayitare | Task 1: preprocessing, exploratory analysis and model training |
| Davy Mugire | Task 2: database design (PostgreSQL and MongoDB) |
| Blessing Ingabire | Task 3: CRUD and time-series API endpoints |
| Davy Mugire | Task 4: prediction / forecast script |

## Dataset

[Beijing PM2.5 Data](https://archive.ics.uci.edu/dataset/381/beijing+pm2+5+data) from the UCI Machine Learning Repository (Chen, 2015, DOI 10.24432/C5JS49).

- Hourly PM2.5 readings from the US Embassy in Beijing, plus weather observations from Beijing Capital International Airport
- 1 January 2010 to 31 December 2014, 43,824 rows, 13 columns
- Only `pm2.5` has missing values (about 4.7%)

The CSV is not stored in this repository. Download it and save it as `data/PRSA_data_2010.1.1-2014.12.31.csv`.

## Repository structure

```
Beijing_forecasting/
├── README.md
├── data/                          (not tracked: put the UCI CSV here)
├── Task1/
│   ├── notebook/Time_series_Project.ipynb
│   └── results/
│       ├── beijing_pm25_model.joblib    (trained model + feature list)
│       └── beijing_records.csv          (original observations)
├── Task2/
│   ├── docker-compose.yml               (PostgreSQL + MongoDB for local use)
│   ├── erd.mermaid                      (ER diagram source)
│   ├── sql/
│   │   ├── schema.sql
│   │   ├── load_sql.py
│   │   └── queries.sql
│   └── mongo/
│       ├── load_mongo.py
│       ├── queries.js
│       └── sample_documents.json
├── Task3/
│   ├── api.py                           (FastAPI app)
│   ├── sql_endpoints.py
│   ├── mongo_endpoints.py
│   ├── common.py
│   └── requirements.txt
└── Task4/
    ├── predict.py                       (fetch, preprocess, load model, predict)
    └── requirements.txt
```

## Setup

Requirements: Python 3.10 or newer, Git, and either Docker or local installs of PostgreSQL and MongoDB.

Run all commands from the repository root unless stated otherwise.

```bash
git clone https://github.com/davy-mgr/Beijing_forecasting.git
cd Beijing_forecasting

python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\activate
# macOS / Linux:         source .venv/bin/activate

pip install -r Task3/requirements.txt -r Task4/requirements.txt
```

This installs everything needed for Tasks 2, 3 and 4. To run the Task 1 notebook yourself, also install `matplotlib` and `jupyter` (it was originally run in Google Colab).

## Task 1: Preprocessing, exploration and model

Notebook: `Task1/notebook/Time_series_Project.ipynb`.

- Builds a timestamp from the year, month, day and hour columns and checks the time range, hourly frequency and missing values
- Fills PM2.5 gaps forward for at most 3 hours when building model inputs; longer gaps are never invented, and the original target is left untouched
- Answers five analytical questions with plots: trend, weather correlations, lag effects, 24-hour and 7-day moving averages, and monthly seasonality
- Forecasts PM2.5 one hour ahead with lag features (1, 6, 24 hours), rolling means (24 and 168 hours), calendar features and previous-hour weather
- Trains a StandardScaler + Ridge regression pipeline, tunes `alpha` and compares feature sets in an experiment table, using a chronological split (train 2010 to 2012, validation 2013, test 2014)

Test results on 2014:

| Model | MAE | RMSE |
|---|---|---|
| Previous-hour baseline | 11.55 | 21.13 |
| Tuned Ridge | 11.69 | 20.83 |

The trained model and its feature list are saved in `Task1/results/beijing_pm25_model.joblib`.

## Task 2: Databases

### Start the databases

With Docker:

```bash
cd Task2
docker compose up -d
cd ..
```

This starts PostgreSQL (port 5432, user `postgres`, password `postgres`, database `beijing_air`) and MongoDB (port 27017), and applies `Task2/sql/schema.sql` automatically on first start. These credentials are for local development only.

Without Docker, install PostgreSQL and MongoDB locally (or use hosted ones such as Neon and MongoDB Atlas), create the `beijing_air` database, run `Task2/sql/schema.sql` against it, and set the connection strings described under Configuration.

### Load the data

```bash
python Task2/sql/load_sql.py data/PRSA_data_2010.1.1-2014.12.31.csv
python Task2/mongo/load_mongo.py data/PRSA_data_2010.1.1-2014.12.31.csv
```

To start over, run `docker compose down -v` in `Task2`, start the containers again and reload.

### Design

**PostgreSQL** (4 tables and 1 view; the ERD source is `Task2/erd.mermaid`, which can be rendered at mermaid.live):

| Table | Purpose |
|---|---|
| `stations` | the two measurement stations (air quality, meteorological) |
| `wind_directions` | lookup for the wind direction codes NE, NW, SE, cv |
| `air_quality_readings` | hourly PM2.5, one row per station and hour |
| `weather_readings` | hourly dew point, temperature, pressure, wind and precipitation |

The view `v_hourly_observations` joins them into one row per hour. Missing PM2.5 values are stored as `NULL`: the database keeps raw data and imputation happens in the preprocessing pipeline.

**MongoDB**: database `beijing_air`, collection `readings`, one document per hour with embedded `calendar`, `air_quality` and `weather` (including `wind`) sub-documents and a unique index on `timestamp`. See `Task2/mongo/sample_documents.json`.

Timestamps are local Beijing time without a time zone and are stored identically in both databases.

### Queries

- SQL: `Task2/sql/queries.sql` (monthly averages, PM2.5 by wind direction, hours above 150, lag and moving average with window functions, latest record)
- MongoDB: `Task2/mongo/queries.js` (latest record, date range with a filter, aggregations by wind direction and by month)

Run the SQL queries with `psql`, SQLTools in VS Code, or:

```bash
cd Task2
docker compose exec -T postgres psql -U postgres -d beijing_air < sql/queries.sql
```

On Windows PowerShell, use `Get-Content sql\queries.sql | docker compose exec -T postgres psql -U postgres -d beijing_air` instead.

For MongoDB, open a shell with `docker compose exec mongo mongosh beijing_air` and paste the queries from `queries.js` one at a time.

## Task 3: API

A FastAPI application with one router per database: `/sql` for PostgreSQL and `/mongo` for MongoDB.

### Configuration

The API reads its connection strings from environment variables.

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/beijing_air"
$env:MONGO_URI="mongodb://localhost:27017"
```

```bash
# macOS / Linux
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/beijing_air"
export MONGO_URI="mongodb://localhost:27017"
```

Set `DATABASE_URL` explicitly: the API's built-in default points at port 5433, while the Docker setup uses 5432.

### Run

```bash
uvicorn api:app --app-dir Task3 --reload
```

Interactive documentation, where every endpoint can be tried, is at http://127.0.0.1:8000/docs. A health check is at `/health`. Keep this terminal open while using the API.

### Endpoints

| Database | Method and path | Purpose |
|---|---|---|
| SQL | `GET /sql/readings/latest` | newest hourly record (PM2.5 and weather) |
| SQL | `GET /sql/readings?start=...&end=...` | records in a date range (start inclusive, end exclusive) |
| SQL | `POST`, `GET /sql/air-quality` | create or list PM2.5 readings |
| SQL | `GET`, `PUT`, `DELETE /sql/air-quality/{reading_id}` | read, update or delete one PM2.5 reading |
| SQL | `POST`, `GET /sql/weather` | create or list weather readings |
| SQL | `GET`, `PUT`, `DELETE /sql/weather/{reading_id}` | read, update or delete one weather reading |
| MongoDB | `GET /mongo/readings/latest` | newest hourly document |
| MongoDB | `GET /mongo/readings?start=...&end=...` | documents in a date range |
| MongoDB | `POST /mongo/readings` | create a document |
| MongoDB | `GET`, `PUT`, `DELETE /mongo/readings/{timestamp}` | read, replace or delete one document |

Timestamps use ISO format, for example `2014-03-04T11:00:00`. See `/docs` for the full request and response formats.

## Task 4: Forecast script

`Task4/predict.py` brings the previous tasks together:

1. Fetches the most recent 192 hourly records from the API (`/readings/latest`, then `/readings?start=...&end=...`)
2. Rebuilds the Task 1 features: forward fill of at most 3 hours, lags, 24 and 168-hour rolling means, previous-hour weather, calendar features
3. Loads `Task1/results/beijing_pm25_model.joblib`
4. Predicts PM2.5 for the next hour

The two APIs return different JSON shapes (flat for SQL, nested for MongoDB), so the script converts both to the same table first.

### Run

Start the databases and the API first (see above), then open a second terminal at the repository root with the virtual environment active:

```bash
python Task4/predict.py --source sql
python Task4/predict.py --source mongo --as-of 2014-03-04T11:00:00
python Task4/predict.py --source csv
```

| Option | Meaning |
|---|---|
| `--source` | `sql` or `mongo` (via the API), or `csv` (reads `Task1/results/beijing_records.csv`, no API needed) |
| `--as-of` | the last observed hour; the forecast is for the following hour (default: the latest record) |
| `--base-url` | API address (default `http://127.0.0.1:8000`, or the `API_BASE_URL` environment variable) |
| `--model`, `--csv` | paths to the saved model and the CSV file |

Example output:

```
Source:             SQL API at http://127.0.0.1:8000 (192 hourly rows fetched)
Last observed hour: 2014-03-04 11:00:00
Forecast for:       2014-03-04 12:00:00
Predicted PM2.5:    15.22 ug/m3
Actual PM2.5:       8.00 ug/m3 (abs. error 7.22)
```

The CSV, SQL and MongoDB sources return the same forecast for the same hour.

## Reference

Chen, S. (2015). Beijing PM2.5 [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5JS49
