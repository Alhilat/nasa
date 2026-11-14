# Dashboard implementation verification

Verified on 2026-11-14 against the local project checkout.

- Frontend: **22 tests passed**, including region drawing/cancellation, date and sensor
  selection, real API request boundaries, missing periods, anomaly withholding,
  archive failures and retry behavior. Test observations are explicitly synthetic.
- Production: `npm --prefix frontend run build` passed TypeScript and Vite compilation.
  Output: `frontend/dist`. MapLibre and ECharts have the expected large-chunk warnings;
  route components are loaded on demand.
- Python: **166 tests passed, 13 PostGIS tests skipped** because `TEST_DATABASE_URL`
  was not configured. SQL selection/lineage, full UTC day matching and CSV transport
  are covered with synthetic unit fixtures. Additional isolated PostGIS assertions
  cover actual exports and persisted grid comparisons when a test database is available.
- Formatting/whitespace: targeted Ruff checks and `git diff --check` passed.
- Browser: actual application screenshots inspected at 1512 and 390 CSS pixels.
  Mobile document width and scroll width were both 390, with no page overflow.
  These browser checks show the real API/database-unavailable state; scientific chart
  values were not substituted. Drawing interactions are covered by component tests
  using a MapLibre test double, rather than a live populated-map browser test.
- Existing FastAPI on port 8000 was reachable but its database readiness failed and
  it served an older API capability set. The updated API was checked separately on
  port 8001. Restart the updated backend and provide PostGIS to view the actual archive.
- Visual QA files were saved locally under ignored `reports/dashboard-qa/`. No private
  `.env` values, real observations or source payloads are included in the frontend bundle.

See [dashboard setup and scientific scope](../dashboard.md) for development and
production routing, completeness requirements, comparison boundaries and exports.
