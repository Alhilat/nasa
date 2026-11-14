# FireScope

Satellite Fire Intelligence Platform foundation for the NASA Space Apps Challenge 2026 project brief: Harmonization of MODIS and VIIRS Hot Spots.

FireScope archives original FIRMS CSV files, separates raw records from normalized observations, supports geographic exploration, and produces reproducible sensor/day/grid summaries. Optional MAP_KEY API synchronization supports recent observations with retries and transactional checkpoints. **No scientific observations are bundled, generated, or downloaded automatically. No machine learning is implemented.** Test fixtures are explicitly synthetic and isolated from the application archive.

## Repository

```text
frontend/         React + TypeScript + Vite + Tailwind, MapLibre, Apache ECharts
backend/          FastAPI, SQLAlchemy/GeoAlchemy, Alembic migrations
data-pipeline/    FIRMS CSV validation, provenance, deterministic aggregation CLI
tests/            Parser, spatial, API, numerical and PostGIS integration checks
docs/             Architecture, API, science methodology, operations and checks
infrastructure/   Dockerfiles, PostGIS Compose stack, SPA server configuration
```

## Start with Docker (recommended)

Install Docker Engine/Desktop with Compose v2. Run every command below from the repository root. The stack uses PostgreSQL 17 + PostGIS 3.5, builds the API and UI, and applies migrations before starting the API.

PowerShell:

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infrastructure/compose.yaml up --build -d
docker compose --env-file .env -f infrastructure/compose.yaml ps -a
Invoke-RestMethod http://localhost:8000/api/v1/health/ready
```

Bash:

```bash
cp .env.example .env
docker compose --env-file .env -f infrastructure/compose.yaml up --build -d
docker compose --env-file .env -f infrastructure/compose.yaml ps -a
curl --fail http://localhost:8000/api/v1/health/ready
```

Open [FireScope](http://localhost:8080), [API documentation](http://localhost:8000/docs), or [public configuration](http://localhost:8000/api/v1/config). A fresh database has sensor metadata only. The explorer displays an empty archive until you import real observations.

If startup fails, inspect `docker compose --env-file .env -f infrastructure/compose.yaml logs migrate api db`. To stop without deleting the archive:

```bash
docker compose --env-file .env -f infrastructure/compose.yaml down
```

The `postgis_data` named volume retains source files, raw rows and job history. Do not remove it if the archive must be kept.

## Import real NASA FIRMS observations

See [the ingestion guide](docs/ingestion.md) for Jordan defaults (complete years 2013–2025), polygon/date filters, strict/quarantine policies, quality reports, duplicate handling and resumable MAP_KEY API imports. Real 2013 Jordan CSV validation reports are included in `docs/reports/`; the current public MODIS country file declares version 6.2 and is correctly rejected when expecting 6.1.

Download a real FIRMS CSV (combined Terra/Aqua MODIS exports are supported with `--sensor MODIS`) from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/content/active_fire/). For VIIRS, select the matching platform. Use `--product-version native` to require and retain per-row product versions, or an exact expected version to reject mismatches. Put your CSV in `data/` under the repository root (create the folder if needed). Nothing in that folder is committed.

Use the exact `version` field from your file, the matching platform, its actual product processing level, a public source location, and the actual retrieval timestamp. The following is a **command template**, not a bundled dataset; replace the path, URL and timestamps with your real source details:

```bash
docker compose --env-file .env -f infrastructure/compose.yaml --profile tools run --rm pipeline ingest /data/your-modis-terra.csv --sensor MODIS_TERRA --source-url https://firms.modaps.eosdis.nasa.gov/content/active_fire/ --product-version 6.1 --processing-level standard --retrieved-at 2026-11-14T08:00:00Z
```

Choose `MODIS` for combined MODIS exports, or `MODIS_TERRA`, `MODIS_AQUA`, `VIIRS_SNPP`, `VIIRS_NOAA20`, or `VIIRS_NOAA21`. VIIRS confidence must use the FIRMS `l/n/h` representation; MODIS uses its native numeric 0–100 scale. The parser validates satellite and instrument, rejects malformed or invalid rows, and imports the entire file in one transaction. Repeated exact payloads share a normalized observation with all original source copies linked. Reimporting the same file with wider filters adds newly selected rows. Changed measurements and NRT/standard versions remain distinct.

Create a versioned common-grid product for a bounded UTC interval (end exclusive):

```bash
docker compose --env-file .env -f infrastructure/compose.yaml --profile tools run --rm pipeline aggregate --start 2024-01-01T00:00:00Z --end 2025-01-01T00:00:00Z --grid-size 0.25
```

Use dates covered by your archive. This produces sensor-specific UTC daily angular grid summaries and source lineage from canonical normalized records. It does **not** calibrate sensor differences, merge distinct revisions/overpasses, estimate burned area, or infer coverage. See [the science contract](docs/science.md).

## Develop locally

Prerequisites: Python 3.12+, Node 22.12+, pnpm 11.25.0, and PostGIS (or start only the Compose database). Keep the root `.env` copied from `.env.example` and use `localhost` in its database URL for a host-run API.

PowerShell, from the repository root:

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infrastructure/compose.yaml up -d db
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend -e ./data-pipeline
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
npm install --global pnpm@11.25.0
pnpm --dir frontend install --frozen-lockfile
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal at the repository root:

```powershell
pnpm --dir frontend dev
```

Bash, from the repository root:

```bash
cp .env.example .env
docker compose --env-file .env -f infrastructure/compose.yaml up -d db
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e ./backend -e ./data-pipeline
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
npm install --global pnpm@11.25.0
pnpm --dir frontend install --frozen-lockfile
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# Separate terminal, from the root:
pnpm --dir frontend dev
```

Open [the development UI](http://localhost:5173). Vite reads the repository root `.env`; `VITE_*` values are public, and must not contain credentials. Use the same CLI locally with `.venv/bin/python -m firescope_pipeline.cli` (PowerShell: `.\.venv\Scripts\python.exe -m firescope_pipeline.cli`) followed by `ingest` or `aggregate` and the flags above. Local file paths replace `/data/...`.

## Run checks

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head --sql
```

Bash:

```bash
.venv/bin/python -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head --sql
```

PostGIS integration tests skip unless `TEST_DATABASE_URL` is set. For the full database-backed suite via Compose:

```bash
docker compose --env-file .env -f infrastructure/compose.yaml --profile test run --build --rm tests
```

Alternatively set `TEST_DATABASE_URL` to a test PostGIS database and run pytest. The tests create and remove their own UUID-named schema. The database user must be able to create schemas and enable PostGIS. GitHub Actions runs this suite against PostGIS and builds/tests the frontend.

See [verification results](docs/verification.md), [architecture](docs/architecture.md), [API contract](docs/api.md), and [operations](docs/operations.md) for implementation limits and deployment details.
