# FireScope scientific dashboard

The root route `/` is the responsive navy/charcoal dashboard. It uses React,
TypeScript, Tailwind, MapLibre GL JS and Apache ECharts. `/explorer`, `/history`,
`/sources` and `/methodology` retain their dedicated workflows and use the same theme.
No demonstration observations or scientific results are served by the UI.

## Build and run

From the repository root:

```powershell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend build
```

The static production bundle is in `frontend/dist`. The existing Compose setup builds
and serves it through nginx, with `/api/` forwarded to the FastAPI `api` service.
Start the PostGIS database and apply migrations using the main README before querying
your archive. Restart an already running FastAPI process after updating its source.

For local development, start FastAPI with the project's existing environment:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
$env:VITE_API_BASE_URL = '/api/v1'
pnpm --dir frontend dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`. If using a different API
port, set `FIRESCOPE_API_TARGET` in that terminal before starting Vite. Production uses
the nginx upstream, not this development proxy. `VITE_API_BASE_URL` can explicitly
select another API deployment; that deployment must allow the frontend origin in
`CORS_ORIGINS`. Existing private `.env` values are preserved, so a previous absolute
URL there still overrides the new same-origin default. Never expose database passwords
or FIRMS keys through `VITE_` environment variables.

## Data and interactions

- Map observations and summary totals share the exact date, region, confidence and
  sensor selection. The end date is inclusive in the UI and exclusive at the API.
  Applying filters or refreshing clears prior responses; failed requests do not turn
  missing totals into zeros. Sections can succeed or fail independently.
- MapLibre supports click-to-draw polygons and rectangles, finishing/cancelling a
  polygon, selecting the viewport and resetting to the study envelope. Bounds and
  GeoJSON fields provide a keyboard alternative. A pending drawn area only becomes
  the analytical selection after **Apply filters**. Existing completeness declarations
  are cleared when the area, confidence or sensor selection changes.
- The initial bounds `[34,29,40,34]` are a Jordan study envelope, not the national
  boundary. Use a polygon for a precise area. Wrapped bounds and split MultiPolygons
  support the antimeridian. Drawing tools reject unsplit antimeridian regions.
- The map caps its displayed page at 2,000 observations and discloses this. Totals
  and detection CSV exports query the full selection. Basemap attribution is retained;
  style failures use a plain coordinate canvas so drawing and real points can still
  work. `VITE_MAP_STYLE_URL` can select an externally hosted or local MapLibre style.
- Historical calendars, trends and anomaly assessments use the entire first and last
  years of the date selection, disclosed above those panels. They retain the same area,
  confidence and sensors. A sensor selector controls the calendar and trend without
  pooling sensor statistics. Select a calendar cell to inspect that exact month.
- Archived monthly counts with unknown completeness are marked `*`; absent observations
  remain null. Color indicates relative archived count for the selected sensor, not risk.
  Missing periods, inadequate history, percentile definitions and coverage declarations
  follow [the historical intelligence contract](historical-intelligence.md).
- Common-grid summary cards and raw/grid charts use a different, explicitly disclosed
  matched scope from a saved aggregate job. They do not claim calibrated activity.
  No saved job, incompatible confidence filters, unsupported algorithms or no overlapping
  full cells/days produces an explicit unavailable/empty state. Recent successful jobs
  are discovered from `/jobs`; an older job UUID can be supplied in Analysis settings.
- Source metadata for the full-year historical selection, processing provenance,
  uncertainty explanations and analysis identity are available next to the outputs.
  Clicking an actual map detection retrieves its source row, original fields and
  uncertainty from `/observations/{id}`. Dedicated archive routes retain all source links.

## Added FastAPI routes

`POST /api/v1/analytics/comparison/{job_id}` accepts `ObservationQuery` with dates and
an area. It compares raw normalized detections with a successful `wgs84-grid-daily-v2`
job. Only wholly contained occupied cells and complete UTC days shared with that job
are used. Raw counts use its source lineage via `EXISTS`, avoiding copy multiplication.
Both counts remain sensor-specific. Confidence filters are rejected because the stored
aggregates cannot be split by class. Differences from the saved archive snapshot are
disclosed; equal counts alone cannot prove source snapshot identity. No calibration,
exposure correction, forecasts or machine learning are applied.

`POST /api/v1/observations/export.csv` accepts the same exact-date/spatial query as
observations and exports all matching detections, capped at 250,000 with a 413 error
for larger selections. Display-page pagination is ignored. CSV includes primary source
SHA-256, original filename, URL, product version, processing level, retrieval timestamp,
native confidence, uncertainty, query and interpretation note. All additional copies
remain accessible in observation detail. Formula-like text is escaped; numeric negative
coordinates and null scientific measurements are preserved.

## Exports and accessibility

- Detection CSV covers exact date filters. Monthly CSV and full analysis JSON cover
  disclosed whole-year history. Calendar CSV checks analysis identity before download.
- Map PNG exports the displayed observation page, selection context, scientific note
  and active style attribution. Drawn regions may still be pending; this is stated in
  the export. Canvas/CORS export failures produce a visible error rather than an empty file.
- ECharts SVG exports include a descriptive title and supplied analytical metadata.
  Every chart offers an accessible data table. Unknown months break trend lines.
- Navigation has a skip link, current-page indication, mobile disclosure and Escape
  handling. Inputs have labels, keyboard-visible focus, status announcements and text
  explanations alongside colors. Reduced-motion preferences disable animation.

## Verification

Unit tests use clearly synthetic software fixtures, isolated from the application archive.
They cover real API transport, empty/error states, sensor and region selection, month
inspection, missing data, region drawing, CSV metadata and equivalent comparison scope.
The optional PostGIS suite exercises exports and a persisted aggregate comparison in its
isolated test schema when `TEST_DATABASE_URL` is available. Browser layout checks at
390 and 1512 CSS pixels cover the real application and its database-unavailable state.
No live scientific result is claimed when PostGIS is unavailable.
