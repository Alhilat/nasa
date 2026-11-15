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

## Missing data, archive completeness, and satellite observation coverage

Archive completeness and satellite observation coverage are kept strictly distinct:

- **Archive completeness (`archive_completeness`)** records whether all FIRMS records from a validated authoritative source stream covering the requested spatial selection, sensor, and full UTC calendar month have been imported into the local archive (`complete`, `partial`, `nrt_complete`, `scope_mismatch`, or `unknown`).
- **Satellite observation coverage (`observation_coverage`)** describes orbital swath, cloud cover, smoke obscuration, and viewing geometry. Without an independent cell-day observability manifest, `observation_coverage` is always reported as `"unknown"`. Archive completeness never proves cloud-free observation or physical fire absence.

During `POST /api/v1/analytics/history` (and offline snapshots with source metadata), the backend reproducibly audits archive completeness from `SourceFile` and `DataQualityReport` provenance (`backend/app/completeness.py`):

1. **Sensor operational availability and partial start months:** Months preceding a sensor's operational start (`MODIS_TERRA` before `2000-11`, `MODIS_AQUA` before `2002-07`, `VIIRS_SNPP` before `2012-01`) are classified as `pre_operational_sensor`. Partial sensor-start months (`MODIS_AQUA` `2002-07` starting `2002-07-04`, `VIIRS_SNPP` `2012-01` starting `2012-01-20`) are classified as `sensor_transition_partial_month` (`archive_completeness: "partial"`, `completeness: "unknown"`).
2. **Annual country files:** A matching successful import report (including the source hash and actual filters) can establish completeness only inside the country boundary. Jordan country files never certify either Jordan rectangular envelope. The three Levant country exports likewise do not certify the larger Levant rectangle.
3. **Bounded FIRMS Area API day windows:** Every full UTC day and the entire selected geometry must be covered by the intersection of the downloaded request and actual import filters. Partial days remain incomplete. Full standard-product months may be complete for the API rectangle itself; this does not make country-only baseline years complete for that rectangle. NRT-only months remain unreconciled. All successful import reports are retained so a wider reimport can add evidence deterministically.
4. **Unknown months preserved as unknown:** Any month without complete source evidence or caller attestation remains `completeness: "unknown"` (`count: null` when zero detections are present) and is excluded from historical baselines and anomaly decisions.

To run and persist the archive completeness audit in PostGIS (`AnalyticalResult` with `result_type = "archive_completeness_audit"`) and write a deterministic report:

```powershell
$env:PYTHONPATH="backend;data-pipeline"
.\.venv\Scripts\python.exe -m firescope_pipeline.cli audit-completeness --start-year 2000 --end-year 2026 --report docs/reports/jordan-archive-completeness.json
```

Callers may also supply explicit `complete_months` overrides scoped to the request:

```json
{"sensor_code":"MODIS_TERRA","month":"2013-01","reference":"your-audit-report#month-2013-01"}
```

## Validated harmonized series vs native sensor series

Historical comparisons check registered `CalibrationModel` entries in PostGIS (or snapshot `calibration_models`):

- Models must have `status == "supported_for_scope"`, evaluated validation without rejections, a verified fingerprint, and explicitly compatible metric, exact region geometry, confidence filter, approved year range, both selected sensors and known product versions. The historical engine currently supports only `monthly_normalized_detection_count` models with `context.history_scope` (`bbox`, `polygon`, `confidence`, `start_year`, `end_year`), `daynight: "all"` and no physical grid. Grid cell-day density and occupancy models are rejected: raw record counts cannot supply their input units or exposure. Supporting these models requires an implementation of their exact training aggregation and observability inputs first.
- When registered models are `candidate_only` (as in the current Jordan and Levant validation studies, which did not pass held-out seasonal and trend gates) or no model covers the scope, the engine retains **separate native sensor series** (`comparison_series: "native_sensor"`) and never pools sensors across transitions.
- Every monthly record, UI comparison card, and CSV/JSON export discloses the `baseline_period`, number of reference years (`baseline_size` and `min_baseline_years`), `missing_data_status`, `observation_coverage`, `comparison_series`, and `limitations`.

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

The audit algorithm is `archive-completeness-v2`; historical analyses use `historical-activity-v2`. The calendar and both trend views plot `comparison_value` against medians and thresholds in the same units. A missing harmonized value remains missing, even if a native count is present. Exports include `comparison_units`. Current Jordan and Levant models remain candidates; these fixes do not establish a validated continuous cross-sensor series.
