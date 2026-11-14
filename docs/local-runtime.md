# Local Windows runtime

FireScope was started on this workstation using portable PostgreSQL 17.12 and
PostGIS 3.6.2 because Docker was unavailable. Binaries and the initialized cluster
are in ignored `data/runtime/`; they are local installation files, not repository
dependencies. The normal Docker setup remains documented in the main README.

The ignored `.env` selects the `firescope_runtime` database on `127.0.0.1:5432`.
It contains development credentials and the FIRMS key; keep it private.

## Restart commands

Run each block in a separate PowerShell terminal. These commands use the existing
installation and cluster; do not run `initdb` again.

Database:

```powershell
Set-Location C:\Users\alhilat\Documents\nasa
& .\data\runtime\postgres\pgsql\bin\postgres.exe -D .\data\runtime\postgres-data -h 127.0.0.1 -p 5432
```

API:

```powershell
Set-Location C:\Users\alhilat\Documents\nasa
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
Set-Location C:\Users\alhilat\Documents\nasa
pnpm --dir frontend dev
```

Open [FireScope](http://localhost:5173/) and [API documentation](http://127.0.0.1:8000/docs).
Readiness is [available here](http://127.0.0.1:8000/api/v1/health/ready).
Services listen on loopback. Stop each foreground process with Ctrl+C;
the database files persist between runs.

## Verified archive

- 26 original NASA FIRMS Jordan CSV files, 2013–2025.
- 9,225 raw and 9,225 normalized observations: 627 MODIS and 8,598 S-NPP VIIRS.
- 6,863 daily sensor/grid aggregates using a 0.25-degree angular grid.
- Six immutable calibration candidates from the Jordan and supplementary Levant studies.
  Neither study supports operational calibration.
- API readiness: HTTP 200, migration revision `0003_calibration`.
- Python verification: 134 passed, including all PostGIS tests.

The map caps displayed observations at 2,000 and reports that limit. Summary totals
cover the complete selection. Narrow date or spatial filters for detailed viewing.
Counts represent thermal detections, not unique fires. Calibration methodology and
validation results are in `harmonization-methodology.md` and `harmonization-results.md`.

Integration tests now keep their Alembic version table inside their UUID-named test
schema. A regression assertion verifies that observations resolve to that schema;
verification also confirmed that the existing public observation count was unchanged.

Official binary sources: [PostgreSQL Windows binaries](https://www.enterprisedb.com/download-postgresql-binaries)
and [OSGeo PostGIS bundle](https://download.osgeo.org/postgis/windows/pg17/postgis-bundle-pg17-3.6.2x64.zip).
For this portable installation, the bundled `bin/postgisgui/libwinpthread-1.dll`
was copied to `bin/libwinpthread-1.dll` to satisfy the PostGIS server dependency.
