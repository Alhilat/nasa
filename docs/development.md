# Local development and checks

Preserve an existing `.env`; copy `.env.example` only for a fresh setup.

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

See [verification results](verification.md), [architecture](architecture.md), [API contract](api.md), and [operations](operations.md) for implementation limits and deployment details.
