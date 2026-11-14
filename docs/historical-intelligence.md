# Historical intelligence

Open `/history` in the application. This engine describes archived thermal detections,
not unique fire events, burned area, ignition probability or future fire risk. Sensor
series stay separate. Existing calibration candidates are not applied automatically.

## API

- `POST /api/v1/analytics/history`: monthly and yearly calendars, seasonal profiles,
  earlier-year reference medians, percentile anomalies, matched-month year-over-year
  changes, spatial concentration and GeoJSON grid cells, source metadata, metric
  explanations and a SHA-256 analysis identifier.
- `POST /api/v1/analytics/history/export.csv`: the same request produces a monthly
  calendar CSV with comparisons, thresholds, version, query and per-month source metadata.
  `X-Analysis-ID` identifies the input snapshot. The browser refuses an export if the
  archive changed since the displayed analysis. Full JSON exports include annual,
  seasonal and spatial results too. The chart toolbar exports an SVG visualization.

Use [history-request.json](history-request.json) as a request body. Its bounding box
is a rectangular WGS84 selection, not the Jordan national boundary. Supply a GeoJSON
Polygon/MultiPolygon for an exact study area. Bounds and polygons intersect. Wrapped
longitude bounds work; antimeridian polygons must be split. Dates use UTC whole months
and years, including leap years. The end year is inclusive. Selection is limited to
50 years and 250,000 observations; larger requests fail with 413, never silently truncate.
Observation pagination parameters are not used. The baseline interval must be inside
the selected interval. For additional baseline years, expand the selection first.

```powershell
$body = Get-Content docs/history-request.json -Raw
Invoke-RestMethod -Uri http://localhost:8000/api/v1/analytics/history -Method Post -ContentType application/json -Body $body
Invoke-WebRequest -Uri http://localhost:8000/api/v1/analytics/history/export.csv -Method Post -ContentType application/json -Body $body -OutFile history.csv
```

## Missing data and completeness

An imported file or a month containing detections does not establish complete archive
coverage. The current schema has no authoritative exposure/completeness ledger. The
default request therefore gives observed counts and spatial summaries, but leaves
comparisons and anomaly decisions unavailable until complete months are declared.
Missing months are null; no interpolation or automatic zero filling is performed.
Positive counts with unknown completeness are still shown and labelled unknown.

After auditing the archive for the exact area, sensor and confidence selection, callers
may supply `complete_months` entries:

```json
{"sensor_code":"MODIS_TERRA","month":"2013-01","reference":"your-audit-report#month-2013-01"}
```

Declarations are scoped to that request, must be unique, and must fall inside its
sensor/year selection. The service retains their references but cannot independently
verify them. These are archive-completeness assertions, not proofs of satellite
exposure, cloud-free observation or absence of physical fires. Only an explicitly
complete empty archive month has a count of zero. Do not infer declarations from
the first/last detection, file names, retrieval dates or consecutive positive months.

## Metrics

- **Monthly count:** normalized exact-payload deduplicated detections. Revisions and
  separate overpasses remain distinct. All linked source copies are retained without
  multiplying counts. Counts do not remove all physical duplicates or sensor bias.
- **Annual count:** only available with twelve complete months. `observed_count`
  is a partial archive total when the year is incomplete; it is never annualized.
- **Seasonal profile:** median and selected complementary percentiles of complete
  instances of each calendar month in the fixed baseline interval, with sample years
  and size. A median can describe even one complete month; thresholds require the
  configured minimum, at least three and default five reference years.
- **Historical reference:** the same sensor, exact selection and calendar month,
  strictly earlier than the target year and inside the baseline interval. Targets,
  future years, incomplete months and other seasons cannot train their own reference.
- **Percentiles:** sort n reference counts and interpolate linearly at `(n-1)*p/100`.
  At p=95 the lower threshold is p=5. Strictly exceeding the upper threshold is
  `unusually_high`, strictly falling below the lower is `unusually_low`; equality is
  `within_range`. Incomplete targets and insufficient history have explicit statuses.
- **Robust z:** `(count-median)/(1.4826*MAD)`, with MAD the median absolute deviation.
  Zero MAD yields null, without disabling valid percentile comparisons. There are
  no Gaussian assumptions or significance claims attached to this descriptive score.
- **Year over year:** monthly differences need complete months in both years. Annual
  differences use only complete calendar months shared by adjacent years and disclose
  that month set and both subtotals. This can be a subset comparison, not an annual
  change. The percent is `100*(current-previous)/previous`; previous zero yields null
  and an explanation, with the absolute difference retained. No matched months yields
  null for all comparison values.
- **Spatial concentration:** fixed angular cells at 0.25, 0.5, 1, 2 or 5 degrees,
  anchored at (-180,-90). For each sensor, a cell share is its count divided by all
  selected detections. The Herfindahl index is the sum of squared cell shares (0–1),
  with the top ten cells' combined share also reported. Empty selections yield null.
  Cell polygons cover the full cell; counts respect the selected area even for cells
  that intersect its boundary. Angular cell areas vary with latitude; these metrics
  are not physical-area-normalized densities or coverage-corrected clusters.
- **Trend visualization:** archived monthly counts, earlier-year medians and the
  upper threshold. Nulls break lines; unknown positive counts remain partial counts.
  No fitted slope, forecast, machine learning, risk model or causal attribution is used.

Percentile flags are descriptive archive anomalies. Small samples, changing effort,
missing coverage, sensor/product changes and revision overlap can change counts.
There is no calibrated false-alarm rate, multiple-testing correction, or operational
fire-risk claim. Each response and CSV retains explanations of these limits.

## Reproduce an analysis

From the repository root, with the configured PostGIS archive available:

```powershell
.\.venv\Scripts\python.exe -m app.history_export --request docs/history-request.json --output reports/history
.\.venv\Scripts\python.exe -m app.history_export --replay reports/history/input-snapshot.json --output reports/history-replay
```

The CLI writes `analysis.json`, `calendar.csv`, and `input-snapshot.json`. The snapshot
contains selected normalized coordinates, UTC timestamps, record hashes, source links
and metadata, not original source bytes or credentials. Replay works without a database
and reapplies spatial, time, confidence and sensor filters. Keep snapshots private if
their locations are sensitive. The same input snapshot and algorithm version give
identical analysis IDs and byte-identical JSON/CSV, without runtime timestamps or random
IDs. Input ordering is normalized; identifiers and source retrieval/import timestamps
are part of the archived snapshot, so a newly imported archive can have a different ID.
This identifier establishes reproducibility, not independent source authenticity.

The engine does not require migrations or write analytical results into the observation
archive. Synthetic tests verify thresholds, missing periods, year matching, sensor and
area separation, source lineage and byte-identical replay. Real PostGIS tests use the
existing isolated-schema integration fixture when `TEST_DATABASE_URL` is set.

For an offline software demonstration, run:

```powershell
.\.venv\Scripts\python.exe -m app.history_export --replay tests/fixtures/history-synthetic-snapshot.json --output reports/history-synthetic
```

This fixture contains fourteen **synthetic test detections**, never imported into the
application archive. January counts are 1, 2, 3 and 8 in 2013–2016. The 2016 January
reference median is 2, the 95th-percentile threshold is 2.9 and its status is unusually
high. All undeclared months remain unknown. These outputs demonstrate reproducibility,
not a measured finding about Jordan or NASA data.
