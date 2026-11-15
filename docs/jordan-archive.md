# Jordan FIRMS archive audit

This audit describes the local `firescope_runtime` database, not data bundled in
Git. Original CSV bytes, source URL, retrieval time, native versions, raw rows,
quality reports and import jobs are stored in PostGIS. The ignored `data/` and
database must be backed up separately. The earlier calibration study and its
fixed 2013–2025 defaults remain unchanged.

## Sources and limits

On 2026-11-14 the [NASA annual country catalog](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt)
listed Jordan MODIS 2000–2025 and S-NPP 2012–2025, with no 2026 annual file.
The 14 newly imported 2000–2012 files, exact URLs, hashes, retrieval timestamps,
native versions and first/last detections are in
[the early-file manifest](reports/jordan-early-archive.json). They contain 232
MODIS and 518 S-NPP source rows, all strictly validated. MODIS is version 6.2;
S-NPP is version 2. Existing 2013–2025 files are documented in
[verification](verification.md). NASA may revise files; a hash identifies the
bytes actually retrieved, not a guarantee that a future download is identical.

NASA's [archive](https://firms.modaps.eosdis.nasa.gov/download/) lists MODIS
from 2000-11-01; NASA identifies Aqua availability from July 2002 and S-NPP
from 2012-01-20 ([NASA Earthdata](https://forum.earthdata.nasa.gov/viewtopic.php?t=5179)).
The first Jordan MODIS detection in these files is 2000-12-03; the first S-NPP
is 2012-01-20. Detection dates do not prove continuous observation coverage.
No NOAA-20 or NOAA-21 history was imported in this S-NPP demonstration.

The annual country files are NASA's Jordan country selection. API imports use
the project's broader `[34.8, 29, 39.4, 33.5]` bounding box and can include
neighboring territory. They are not a border-exact continuation; use a trusted
polygon consistently for a geographic comparison. The API stores standard
and near-real-time (NRT) revisions separately. They are not automatically
reconciled, and their counts must not simply be summed in overlapping periods.
FIRMS says NRT data is subsequently replaced by standard products, usually
after 2–3 months but sometimes up to 5 months ([NASA](https://firms.modaps.eosdis.nasa.gov/content/active_fire/)).

An annual file or successful API response establishes only that those bytes
were retrieved and processed. Cloud, observation, processing and other gaps
are not audited; months without records remain unknown, not zero fires. The
application requires explicit completeness declarations before using months in
comparative statistics. The earliest and latest detections are not coverage
boundaries.

## Verified local coverage

The 2026 API imports completed with the four checkpoint intervals in
[the coverage snapshot](reports/jordan-archive-coverage.json). Availability
returned by NASA on 2026-11-14 was MODIS standard through August 31 and NRT
September 1–November 14; S-NPP standard through July 31 and NRT August 1–November 2.
S-NPP November 3 onward was unavailable from the queried sources at that time.
The latest dates may be partial and availability can change. All API windows
were processed, but a successful window does not establish observational
completeness. The snapshot lists months with no archived detections per sensor;
all such months have unknown status, including months before a sensor began.

| Sensor | Archived normalized detections | First detection UTC | Last detection UTC |
| --- | ---: | --- | --- |
| MODIS Terra | 639 | 2000-12-03 08:17 | 2026-11-11 06:24 |
| MODIS Aqua | 551 | 2002-07-23 23:39 | 2026-11-14 12:40 |
| VIIRS S-NPP | 11,889 | 2012-01-20 23:16 | 2026-11-02 10:15 |

These 13,079 detections combine different spatial selections and product
revisions; they are not unique fires. The 2026 API rows declare MODIS standard
`61.03`, MODIS NRT `6.1NRT`, S-NPP standard `2`, and S-NPP NRT `2.0NRT`.
These native values are preserved verbatim. The dashboard date limits follow
the first and last archived detections, not an independent coverage audit. Old
grid aggregate jobs have not been recomputed for the extended period.

## Reproduce and update

Install and migrate using [ingestion setup](ingestion.md), with PostGIS running
and `DATABASE_URL` configured in `.env`. The annual importer consults NASA's
catalog, records absent years in its ledger, downloads original bytes, strictly
validates native versions and imports without the historical profile's 2013
start filter. It saves a catalog snapshot and an incremental ledger under the
ignored output directory. Repeated runs verify cached hashes and reuse their
original retrieval times; remove neither cached files nor ledger independently.
Use a new output directory to fetch a fresh copy and compare revisions.

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.jordan_archive --start-year 2000 --end-year 2025 --output data/jordan-archive
```

For the API obtain a [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key/)
and set it only in the ignored `.env`. Check NASA's current
[availability](https://firms.modaps.eosdis.nasa.gov/api/data_availability) for
each product and choose dates within its inclusive limits. End dates below are
exclusive. These were the observed source intervals on 2026-11-14:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli sync-api --source MODIS_SP --profile jordan --start 2026-01-01 --end 2026-09-01 --resume --window-days 5 --report reports/archive-MODIS_SP.json
.\.venv\Scripts\python.exe -m firescope_pipeline.cli sync-api --source VIIRS_SNPP_SP --profile jordan --start 2026-01-01 --end 2026-08-01 --resume --window-days 5 --report reports/archive-VIIRS_SNPP_SP.json
.\.venv\Scripts\python.exe -m firescope_pipeline.cli sync-api --source MODIS_NRT --profile jordan --start 2026-09-01 --end 2026-11-15 --resume --window-days 5 --report reports/archive-MODIS_NRT.json
.\.venv\Scripts\python.exe -m firescope_pipeline.cli sync-api --source VIIRS_SNPP_NRT --profile jordan --start 2026-08-01 --end 2026-11-03 --resume --window-days 5 --report reports/archive-VIIRS_SNPP_NRT.json
```

For future runs, extend each end only within current availability and retain the
same source, area and anchor start for its checkpoint. Resume replays two days
by default; if a rolling NRT source no longer offers that lookback, use an
available interval and a new anchor. Import newly available standard periods
separately and document the revision overlap. For long intervals a request
budget may require repeated `--resume` runs. API requests, selected date windows,
retrieval timestamps, versions, original bytes and checkpoints are stored in
the database; reports are in ignored `reports/`. API URLs intentionally omit
the key, while source, area and dates are retained as request metadata.

## Reproducible archive completeness audit

To audit and record archive completeness by area, sensor, and UTC month from
stored `SourceFile`, `DataQualityReport`, and `ImportCheckpoint` evidence without
conflating archive ingestion completeness with satellite observation coverage:

```powershell
$env:PYTHONPATH="backend;data-pipeline"
.\.venv\Scripts\python.exe -m firescope_pipeline.cli audit-completeness --start-year 2000 --end-year 2026 --report docs/reports/jordan-archive-completeness.json
```

See [Jordan archive completeness report](reports/jordan-archive-completeness.json)
for the recorded area-by-sensor-by-month audit snapshot (`audit_id`
`51bf0da76460e82818058c84cbd32d189e273600e47e83d019972afa2849e7f5`).

The v2 audit requires the exact source footprint and actual import filters. Neither Jordan rectangle is fully covered by the archived country files. Use the Jordan polygon for supported historical comparisons; the larger study rectangle currently has no source-certified complete months.
