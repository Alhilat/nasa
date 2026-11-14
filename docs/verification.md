# Foundation verification

This file records checks actually run in the development environment on 2026-11-14 and separates checks that require external infrastructure.

## Results

| Check | Observed result |
| --- | --- |
| Python suite (`python -m pytest -q`) | **101 passed, 10 skipped** |
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
| Explorer browser review | **Passed** for basemap rendering, explicit archive failure, disabled empty export, spatial controls and invalid-bbox feedback |
| Source/job view browser review | **Passed** navigation and explicit unavailable states |
| Methodology browser review | **Passed**, references and method/uncertainty descriptions rendered |
| Responsive review | **Passed** at 1440×1000 and 390×844; mobile document width 375px in a 390px viewport (no horizontal overflow), navigation opens/closes and is hidden from accessibility when closed |
| Actual PostGIS migrations, ingestion and spatial execution | **Not run**; no Docker or database available |
| GitHub Actions execution | **Not run**; workflow supplied, no remote repository configured |

The development host has no Docker executable and no configured PostGIS service. Database runtime integration checks cannot be claimed as passed here. The repository provides those checks and a PostGIS-backed CI workflow; CI execution is not claimed unless observed.

The ten integration tests cover real database migration/application queries, polygon holes and boundaries, wrapped bboxes, paging and summary results, exact archived bytes, mutation triggers, idempotence, failed-job rollback, aggregate lineage and null FRP. They are collected and skip explicitly without `TEST_DATABASE_URL`. Run the documented Compose test command before relying on database-backed behavior.

## Observed non-failing notices

- The installed Starlette release reports a TestClient deprecation notice for `httpx`. API tests pass; a future dependency update should evaluate its supported test transport.
- Vite reports the dedicated MapLibre bundle exceeds its 500 kB advisory chunk size. The production build succeeds. Map and ECharts dependencies are split into separate chunks; further route-level lazy loading is future optimization.

## Visual evidence and data policy

Browser QA snapshots: [desktop explorer](screenshots/explorer-desktop.png) and [mobile source catalog](screenshots/sources-mobile.png). The visible disconnected state reflects the actual unavailable database. The basemap is geographic context, not a scientific fire-observation layer.

No real observation file was inserted into an application database during development. For the ingestion extension, two real NASA Jordan 2013 country CSVs were downloaded unchanged and validated locally; see `docs/reports/` and `docs/ingestion.md`. The S-NPP file has 566 valid records, while the MODIS file declares 6.2 and its 19 rows were correctly rejected when expecting 6.1. No synthetic observation was inserted into a running application database. Synthetic numerical/CSV fixtures exist only in the test suite and are marked as test-only. Temporary API/UI servers used for verification were stopped after QA.

## Ingestion extension checks (2026-11-14)

The updated Python suite includes strict/native version checks, combined MODIS platforms, Jordan overlap selection, polygon/time semantics, bounded quality reports, explicit invalid-row handling, sensor-specific fields, mocked NASA API retries/quotas/availability, MAP_KEY error/log redaction and checkpoint/lookback orchestration. The latest result is 101 passed, 10 integration tests skipped. Frontend boundary tests remain 4 passed, and TypeScript/Vite production build passes after updating duplicate-policy text. Dependency consistency and Alembic offline SQL generation through `0002_ingestion` pass.

The documented real-file `validate` CLI commands were executed: VIIRS S-NPP returned exit 0; explicit MODIS 6.1 validation returned the expected exit 1 and a JSON version-mismatch report. Their checksums/source locations are recorded in committed reports. Actual raw/normalized persistence, backfill and atomic checkpoint behavior require the supplied PostGIS integration suite; they were not exercised on a running database here. Live MAP_KEY requests were not executed; HTTP behavior was tested with mocked transport. No fake observations were substituted for unavailable data.
