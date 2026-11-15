# NASA FIRMS ingestion

For the extended Jordan archive, actual imports, gaps and update commands, see
[Jordan archive audit](jordan-archive.md). The old Jordan historical profile below
remains a fixed calibration selection; it must not be used unmodified for earlier
or current-year file imports.

The ingestion module supports official MODIS Collection 6.1 CSV exports, VIIRS S-NPP 375 m CSVs, NOAA-20/21 CSVs, and optional recent/standard FIRMS area API sources. Source bytes and every parsed native field are retained. Normalized records, raw source records, provenance links and quality reports are separate database objects.

## Start and migrate

From the repository root, copy `.env.example` to `.env` if it does not exist. With Docker installed:

```powershell
docker compose --env-file .env -f infrastructure/compose.yaml up --build -d
```

For an existing installation, rebuild and apply the new migration before using the ingestion code:

```powershell
docker compose --env-file .env -f infrastructure/compose.yaml build migrate api pipeline
docker compose --env-file .env -f infrastructure/compose.yaml run --rm migrate
docker compose --env-file .env -f infrastructure/compose.yaml up -d api frontend
```

For a host-run installation with an existing `.venv` and PostGIS:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend -e ./data-pipeline
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

On Bash substitute `.venv/bin/python` for `.\.venv\Scripts\python.exe`. The database-backed CLI entry point is `python -m firescope_pipeline.cli`; examples below use the PowerShell executable path. Docker equivalents use `docker compose --env-file .env -f infrastructure/compose.yaml --profile tools run --rm pipeline` followed by the same subcommand/options, with `/data/...` and `/reports/...` paths.

## Jordan starter and years

`--profile jordan` selects the study envelope `[34.8,29.0,39.4,33.5]` in WGS84 and, for historical commands, the complete calendar-year interval **2013-01-01T00:00:00Z through 2026-01-01T00:00:00Z, end exclusive**. These are study defaults for complete years overlapping MODIS and S-NPP availability, not a guarantee of complete sensor coverage. The envelope includes neighboring territory; provide a trusted Jordan border Polygon/MultiPolygon using `--polygon` for a border-exact selection. Polygon files must be GeoJSON geometries, not Features. Bbox and polygon filters intersect. Explicit `--bbox`, `--start` and `--end` override profile values.

NASA lists MODIS history from November 2000 and S-NPP history from January 2012. Query current API availability rather than extrapolating those dates to recent data. Additional platforms have different coverage. [NASA archive download](https://firms.modaps.eosdis.nasa.gov/download/), [API availability](https://firms.modaps.eosdis.nasa.gov/api/data_availability).

## Official historical files

Obtain Collection 6.1 CSVs through [NASA FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/) or the [official yearly country downloads](https://firms.modaps.eosdis.nasa.gov/country/). The archive service may require the operator’s Earthdata/email login. No credentials are collected by this pipeline. Keep original downloads in `data/`, which is ignored by Git and not served by the frontend.

MODIS historical files can contain both Terra (`T`/`Terra`) and Aqua (`A`/`Aqua`). Use `--sensor MODIS` for these combined exports; normalized rows retain the individual satellite. Use `MODIS_TERRA` or `MODIS_AQUA` only for single-platform files. VIIRS choices are `VIIRS_SNPP`, `VIIRS_NOAA20`, and `VIIRS_NOAA21`.

Validate a genuine Collection 6.1 file without a database:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli validate data/your-modis-c61.csv --sensor MODIS --product-version 6.1 --profile jordan --report reports/modis-c61-quality.json
```

Import the same file after validation. Replace the filename, source location and retrieval time with your actual source metadata:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli ingest data/your-modis-c61.csv --sensor MODIS --product-version 6.1 --processing-level standard --source-url https://firms.modaps.eosdis.nasa.gov/download/ --retrieved-at 2026-11-14T08:00:00Z --profile jordan --report reports/modis-c61-import.json
```

VIIRS standard CSV example (use its actual version field; `native` requires and preserves every row’s declared version):

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli ingest data/your-viirs-snpp.csv --sensor VIIRS_SNPP --product-version native --processing-level standard --source-url https://firms.modaps.eosdis.nasa.gov/download/ --retrieved-at 2026-11-14T08:00:00Z --profile jordan --report reports/viirs-snpp-import.json
```

Custom selection example:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli validate data/your-modis-c61.csv --sensor MODIS --product-version 6.1 --bbox 34.8,29,39.4,33.5 --polygon data/jordan-border.geojson --start 2018-01-01T00:00:00Z --end 2019-01-01T00:00:00Z --report reports/jordan-2018.json
```

All rows are validated before selection, and every accepted source’s raw records are archived, including out-of-selection rows. Only valid selected rows enter the normalized table. A later import of the same file with a wider selection adds the newly selected observations without duplicating earlier normalized records. There is no timestamp high-water mark that would discard late historical records.

### Real Jordan validation performed in this workspace

The official NASA country manifest was inspected, and its listed 2013 Jordan MODIS/S-NPP files were downloaded unchanged to `data/jordan/2013/`. Retrieval URLs, timestamps and SHA-256 checksums are retained in `data/jordan/2013/sources.json`. Reports are committed under `docs/reports/`:

| Download | Observed result on 2026-11-14 |
| --- | --- |
| `viirs-snpp_2013_Jordan.csv` | 566 rows; native version `2`; 566 valid; 0 invalid; 0 exact in-file duplicates |
| `modis_2013_Jordan.csv` | 19 rows; file declares version `6.2`; all 19 rejected when explicitly expecting Collection `6.1` |

The current yearly MODIS file must **not** be relabeled as Collection 6.1. The mismatch demonstrates the import guard; it does not establish that the file’s measurements are invalid. Use an actual C6.1 archive export for the requested C6.1 study. These observations were validated only, not inserted into a database because no PostGIS service was available.

Reproduce the recorded validations locally:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli validate data/jordan/2013/viirs-snpp_2013_Jordan.csv --sensor VIIRS_SNPP --product-version 2 --profile jordan --report reports/snpp-2013.json
.\.venv\Scripts\python.exe -m firescope_pipeline.cli validate data/jordan/2013/modis_2013_Jordan.csv --sensor MODIS --product-version 6.1 --profile jordan --report reports/modis-2013-version-check.json
```

The second command intentionally exits 1 and writes the version mismatch report. Source URLs: [S-NPP CSV](https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2013/viirs-snpp_2013_Jordan.csv), [MODIS CSV](https://firms.modaps.eosdis.nasa.gov/data/country/modis/2013/modis_2013_Jordan.csv), [NASA’s file manifest](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt). Downloads may be revised; compare hashes with the recorded reports.

## Optional MAP_KEY API integration

Obtain a key from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/map_key/). Set the server-only `MAP_KEY` in the root ignored `.env`, or supply it through an environment/secret manager. Never put it in a `VITE_*` value, source URL, command argument, report, or source control. The CLI loads `.env` without overriding existing environment variables. Compose passes the key only to the pipeline service.

```dotenv
MAP_KEY=your_actual_key
```

Choose dates within current source availability; the following shows the CLI shape rather than claiming observations exist in that interval:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli sync-api --source MODIS_NRT --profile jordan --start 2026-11-01 --end 2026-11-03 --resume --lookback-days 2 --max-requests 200 --report reports/recent-modis.json
```

Use `VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`, or `VIIRS_NOAA21_NRT` for recent VIIRS. The corresponding `_SP` identifiers are also supported where NASA’s availability endpoint permits them. Recent profile mode uses only the Jordan spatial envelope; its dates come from the required API flags, not the historical profile interval.

Each API request fetches one UTC date by default; `--window-days 5` requests up to five days per call, including a shorter final window. NASA documents 5,000 transactions per 10 minutes; multi-day calls may cost multiple transactions. This client paces attempts at least one second apart and caps attempts per invocation (default 200), including retries. It retries network timeouts and HTTP 408/429/500/502/503/504 with bounded exponential backoff/jitter. `Retry-After` seconds or HTTP dates are honored. If NASA asks for more than 60 seconds, the client stops with a resume-later message rather than retrying early. A 429 without `Retry-After` is treated as a possible 600-second quota window. Permanent HTTP errors, redirects and HTTP-200 error text are rejected. [NASA area API contract](https://firms.modaps.eosdis.nasa.gov/api/area).

The API base host is fixed to NASA HTTPS, redirects are disabled, timeouts are bounded, and each response is capped at 50 MiB after HTTP decompression. CSV bytes are stored unchanged. No key-bearing URL or error body is persisted; HTTPX/httpcore diagnostic logs have a key-redaction filter. Availability is checked before downloading the requested interval. If a source ends or has no requested date, the client reports it rather than fabricating data or switching satellites.

### Checkpoints and late data

The checkpoint key includes source, exact area/polygon, parser policy and the requested starting date. Increasing `--end` with the same starting date resumes the same stream. Changing the area/source/start begins a different stream. Each successful day’s archive, raw rows, normalized records, quality report and checkpoint advancement commit together. Failures stop subsequent windows and do not advance the failed day. Earlier committed days remain available. Use `--resume` after resolving a failure.

Resume re-fetches the last two committed dates by default to capture late/revised detections. `--lookback-days 0` resumes at the next unprocessed day; larger lookbacks up to 30 days are supported. Re-fetching is safe because exact records de-duplicate. A checkpoint proves a successfully processed API response, **not** complete fire coverage or absence of fire. Header-only CSV responses archive zero raw rows and can advance a checkpoint; plain error text never does. Network failures before a CSV arrives produce a CLI error/report but do not invent a source file/job.

## Storage, duplicates and migration

- `source_files`: byte-for-byte CSV archive and source context. Uniqueness includes checksum, declared sensor/family, product and processing level so identical header-only responses for different sensors do not conflict. Every import attempt also retains its retrieval/request metadata in its processing job.
- `raw_records`: one immutable payload per source data-record number, including all sensor-specific and unknown columns. Raw records and source bytes remain even when explicit quarantine excludes invalid rows from normalization.
- `normalized_observations`: validated WGS84/UTC fields and native confidence, uncertainty metadata, and canonical record hash. No original payload JSON is stored in this table.
- `observation_records`: immutable links from every raw copy to its canonical normalized observation.
- `data_quality_reports`: immutable per-job JSON report, including rejected imports.
- `import_checkpoints`: transactional API stream progress.

Canonical identity uses SHA-256 of a PostgreSQL JSONB representation of the resolved satellite, native product version, processing level and **entire original parsed field/value object**. Column order, file line endings and CSV quoting differences do not create new normalized records. Different field sets, numeric text, measurements, versions, overpass times, platforms or processing levels remain distinct. Same-coordinate/time records with changed fields are not silently merged, and NRT is not silently replaced by standard processing. This is intentionally conservative; semantic cross-product matching still requires scientific review.

Exact repeated payloads share one normalized observation but retain all raw copies and source links. API observation details expose `source_copies` and `record_hash`. Summary/source counts and new grid jobs use canonical observations and linked raw-source lineage. Grid method version is `wgs84-grid-daily-v2`; existing derived jobs remain unchanged.

Migration `0002_ingestion` backfills raw records and canonical normalized observations from the original immutable `raw_observations` table. That legacy table is preserved unchanged and no longer receives new pipeline inserts. Existing aggregate jobs retain their original meaning. Backfill keeps the lowest original observation ID for exact duplicate payloads; duplicate legacy IDs remain in the legacy archive/raw records. Downgrade is refused because dropping the new archive objects would lose provenance. Back up before upgrading a populated archive.

## Validation and quality reports

Validation checks finite WGS84 coordinates, valid calendar dates/UTC HHMM times, nonnegative finite FRP (zero is valid), positive finite scan/track/temperature values when supplied, matching satellite/instrument metadata, exact requested version, native confidence scheme, and valid day/night values. A version marked RT/URT/NRT cannot be declared standard processing. Undocumented missing-value sentinels are rejected. Empty optional measurements stay null; missing observations are never generated.

Default `--on-error reject` fails the entire import before archiving/normalizing new records. The separately committed failed job retains its quality report. `--on-error quarantine` explicitly archives all structurally valid raw rows, imports valid selected rows only, and reports the exclusions. Malformed headers, encoding, quoting, NULs, column counts, file sizes or record counts reject the whole file even in quarantine mode. API sync always uses strict mode.

Reports include checksums, observed versions, total/valid/invalid/selected/excluded counts, per-sensor counts, missing FRP, exact duplicate counts, same-sensor/time/position repetitions, acquisition extents, filters, issue counts and up to 100 row-numbered issue examples. Import reports additionally show new raw/normalized counts and selected records already represented. Limits: 50 MiB / 250,000 data records per file. Every accepted or row-rejected import has a database quality report; `--report` also writes JSON atomically to disk. `validate` needs no database and exits 1 on invalid rows.

Read reports using `GET /api/v1/quality-reports/{job_id}` or the processing job’s output metadata. Validation can establish internal consistency and file identity, not physical fire truth, sensor coverage or a calibrated uncertainty estimate.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
docker compose --env-file .env -f infrastructure/compose.yaml --profile test run --build --rm tests
```

Unit tests use explicitly synthetic CSVs and mocked HTTP transport. No test makes a live MAP_KEY call. PostGIS tests run when `TEST_DATABASE_URL` is set and exercise migrations, raw/normalized separation, exact duplicate links, conservative revisions, widening selections, failed reports, immutable archives and atomic checkpoints. This workspace has no Docker/PostGIS, so those integration tests are supplied and collected but skipped locally. Real downloaded CSV validation results are the separate reports described above.
