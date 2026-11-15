# Foundation verification

## November 15, 2026 judge update

- The Python suite passed **285 tests** against isolated disposable PostGIS
  schemas. Three existing Alembic deprecation warnings were non-failing.
- The frontend suite passed **88 tests** after the median-color and multi-sensor
  table changes. TypeScript and the Vite production build passed; Vite retains
  its advisory warning about large map/chart chunks.
- Required undefined-name Ruff checks passed for API, pipeline and tests. The new
  median statistics module and its tests also passed full Ruff checks.
- A real Jordan backfill through November 15 resumed successfully: 40 annual
  files were skipped from verified checkpoints, all four API ranges were up to
  date, and explicit gaps remained. The archive contains 13,079 detections and
  164 source records. [Measured backfill summary](reports/backfill-judges-summary.json).
- Browser review covered the live dashboard, median-departure calendar and source
  catalog. All 156 exported harmonized monthly CSV rows matched the API response,
  including median context; 96 months were assessed and the calibration remained
  experimental. [Exact query and comparison record](reports/judges-calendar-verification.json).
- [Fresh screenshots](screenshots/README.md) and the [judge requirement matrix](judges.md)
  document the current build. Docker and remote CI execution remain unverified
  on this host; no forecast accuracy or full WCAG audit is claimed.

## Earlier foundation record

This file records checks actually run in the development environment on 2026-11-14 and separates checks that require external infrastructure.

## Results

| Check | Observed result |
| --- | --- |
| Python suite with `TEST_DATABASE_URL` | **134 passed, no skips** |
| Frontend API-boundary tests (`pnpm --dir frontend test`) | **4 passed** |
| TypeScript + Vite production build (`pnpm --dir frontend build`) | **Passed** |
| Alembic `upgrade head --sql` | **Passed**; output committed as `docs/schema.sql` |
| Bytecode compilation of API, pipeline and migrations | **Passed** |
| `python -m pip check` | **Passed**, no broken requirements |
| Compose and GitHub Actions YAML parsing | **Passed** syntax parsing; Compose itself unavailable |
| Pipeline CLI `--help` | **Passed** |
| HTTP frontend root | **200**, FireScope HTML served |
| HTTP `/api/v1/health/live` | **200** |
| HTTP `/api/v1/config` | **200**, public science/capability configuration |
| HTTP `/api/v1/health/ready` without PostGIS | **503**, sanitized database-unavailable response |
| HTTP `/api/v1/health/ready` with local PostGIS | **200**, revision `0003_calibration` |
| Explorer browser review | **Passed** for basemap rendering, explicit archive failure, disabled empty export, spatial controls and invalid-bbox feedback |
| Source/job view browser review | **Passed** navigation and explicit unavailable states |
| Methodology browser review | **Passed**, references and method/uncertainty descriptions rendered |
| Responsive review | **Passed** at 1440×1000 and 390×844; mobile document width 375px in a 390px viewport (no horizontal overflow), navigation opens/closes and is hidden from accessibility when closed |
| Actual PostGIS migrations, ingestion and spatial execution | **Passed**, portable PostgreSQL/PostGIS runtime |
| GitHub Actions execution | Workflow supplied; remote CI execution is not asserted here |

The development host has no Docker executable. A portable PostgreSQL 17.12/PostGIS 3.6.2 installation now provides local database verification. See [local runtime commands](local-runtime.md).

The eleven integration tests cover real database migration/application queries, polygon holes and boundaries, wrapped bboxes, paging and summary results, exact archived bytes, mutation triggers, idempotence, failed-job rollback, aggregate lineage, null FRP and calibration registration. All passed locally. They skip explicitly without `TEST_DATABASE_URL`.

## Observed non-failing notices

- The installed Starlette release reports a TestClient deprecation notice for `httpx`. API tests pass; a future dependency update should evaluate its supported test transport.
- Vite reports the dedicated MapLibre bundle exceeds its 500 kB advisory chunk size. The production build succeeds. Map and ECharts dependencies are split into separate chunks; further route-level lazy loading is future optimization.

## Visual evidence and data policy

Earlier browser QA snapshots: [desktop explorer](screenshots/explorer-desktop.png) and [mobile source catalog](screenshots/sources-mobile.png). Those snapshots show the database-unavailable stage. The current running explorer was also verified with 9,225 NASA observations, summary totals, map points and daily charts. The basemap is geographic context.

The running `firescope_runtime` archive contains 26 official Jordan CSVs from 2013–2025, preserving 9,225 raw and normalized observations, plus 6,863 daily sensor/grid aggregates and six calibration candidates. Every source URL was checked against the NASA FIRMS origin. During initial runtime verification, a test-isolation bug allowed synthetic fixtures into the first local database: a public Alembic version table caused migrations for the intended test schema to be skipped. The fixture now explicitly scopes its version table and asserts observation-table ownership. The running archive was rebuilt in a separate clean database, and the rerun confirmed the existing public observation count was unchanged by tests. Services remain running at the user's request.

## Earlier ingestion extension checks (2026-11-14, before local database setup)

The updated Python suite includes strict/native version checks, combined MODIS platforms, Jordan overlap selection, polygon/time semantics, bounded quality reports, explicit invalid-row handling, sensor-specific fields, mocked NASA API retries/quotas/availability, MAP_KEY error/log redaction and checkpoint/lookback orchestration. The latest result is 101 passed, 10 integration tests skipped. Frontend boundary tests remain 4 passed, and TypeScript/Vite production build passes after updating duplicate-policy text. Dependency consistency and Alembic offline SQL generation through `0002_ingestion` pass.

The documented real-file `validate` CLI commands were executed: VIIRS S-NPP returned exit 0; explicit MODIS 6.1 validation returned the expected exit 1 and a JSON version-mismatch report. Their checksums/source locations are recorded in committed reports. Actual raw/normalized persistence, backfill and atomic checkpoint behavior require the supplied PostGIS integration suite; they were not exercised on a running database here. Live MAP_KEY requests were not executed; HTTP behavior was tested with mocked transport. No fake observations were substituted for unavailable data.

## Statistical harmonization extension (2026-11-14)

- Before local database setup: **123 passed, 11 skipped**. After setup: **134 passed**, including registration and immutability checks. Six study models were also registered in the clean application archive with status `candidate_only`.
- Frontend: **4 passed**; TypeScript/Vite production build passed after methodology copy changes. Existing MapLibre bundle-size advisory remains non-failing.
- Python bytecode compilation, `pip check`, and Alembic offline SQL through `0003_calibration` passed.
- The supplied MAP_KEY successfully queried real FIRMS availability for MODIS/S-NPP standard and NRT sources. One bounded historical MODIS API sample was downloaded and its native version recorded. The key remains in ignored `.env`; no key value is present in Git-visible source/report files or the exported report/model artifacts checked.
- Official, hash-verified standard-product country CSVs for 2013–2025 were analyzed: Jordan has 9,225 input normalized detections; the separate Jordan/Syria/Lebanon transfer study has 224,509. These are observations, not unique fire events.
- Jordan: 95 paired daytime region-month bins, 529 unknown/unpaired calendar bins; temporal MAE falls from 0.296360 to 0.043050 for the validation-selected regression. Spatial support, trend support, coverage and product-scope gates prevent operational approval.
- Supplementary Levant: 326 paired bins. Lebanon is held out, with 44 spatial-test bins and 31 joint year/region-test bins. Validation selects quantile mapping; its temporal MAE is 0.048040 versus 0.556002 baseline, but matched-month Syria temporal slope error increases by about 19.5%, failing the preset trend gate. No calibration is automatically enabled.
- The final Jordan study was rerun in another output directory. Its study ID and **all 16 artifact hashes** matched exactly, including tables, fitted JSON models, PNGs and SVG. This verifies reproducibility for the archived inputs and locked environment, not future mutable downloads or other OS/BLAS/font versions.
- Before/after and held-out-error figures were visually inspected. Original CSVs and complete normalized observation audit tables remain in ignored `data/` / `reports/`. Curated plots, metrics, paired tables, models, geometries and source manifests are under `docs/reports/harmonization/`.

See [methodology](harmonization-methodology.md) and [measured results](harmonization-results.md) for definitions, acceptance criteria, limitations and exact reproduction/registration commands.
