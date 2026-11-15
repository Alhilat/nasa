# Site foundations: implementation and verification

Date: 2026-11-15 (Asia/Amman). This records the first implementation batch of the
[site-improvement plan](site-improvement-plan.md), not completion of the full roadmap.

## Changes

- Validate `index.html` and every referenced compiled script/stylesheet during the
  native and Docker builds. Production startup requires the built website.
- Expose public API/frontend status and commit identity at `/api/v1/health/build`.
- Add a read-only deployment smoke command covering all five GET/HEAD page routes,
  compiled assets, database readiness, source queries, missing API routes and tiles.
- Exercise the combined artifact in CI with a disposable PostGIS database.
- Add migration `0004_backend_access`: default-deny RLS and removal of browser-role
  table grants for the 14 application tables; pin application trigger search paths.
- Add a reusable read-only source-byte, row-count, canonical identity and lineage
  reconciliation command. See [release instructions](release-checklist.md).

Application commits: `d5d4242` and the migration concurrency correction `d734aa2`.

## Verification

- Local suite: 338 passed, 20 database integration tests skipped because the local
  disposable database was unavailable. No test fixtures were inserted into Supabase.
- GitHub Actions [corrected-release run](https://github.com/Alhilat/nasa/actions/runs/43746285142):
  both `python-postgis` and `frontend` jobs passed, including the actual PostGIS
  permission/concurrency/importer tests and the combined production artifact smoke.
- Initial release attempt encountered a deadlock between incremental DDL locks and
  an existing historical query. PostgreSQL rolled it back; revision stayed at
  `0003_calibration`, and Render retained the previous live version. No archive rows
  were changed. The correction uses all-table NOWAIT acquisition with savepoints
  and bounded retries; CI verifies partial locks are released when readers are busy.
- Corrected deploy `dep-dbsvh7t6e07s73b0tfcg` became live at 21:26 Asia/Amman.
  The live build endpoint reports `d734aa2d1bbc49b597582a834a180c94183fb569`,
  frontend `ready`, and database revision `0004_backend_access`.
- The production smoke command passed for that exact commit, including all five
  GET/HEAD routes, referenced assets, source query, readiness, unknown API 404 and
  an actual basemap image. The read-only archive reconciliation passed again.
- Production catalog checks confirm 14 application tables have RLS enabled and
  zero effective SELECT/INSERT/UPDATE/DELETE/TRUNCATE table grants to either
  `anon` or `authenticated`. The owner-based API source query still succeeds.
- Supabase's application trigger search-path warnings cleared. Its no-policy
  informational notices reflect intentional backend-only default deny. Remaining
  security advisories concern the extension-owned `spatial_ref_sys`, the public
  PostGIS extension and executable SECURITY DEFINER `st_estimatedextent` overloads.
  Those are not represented as resolved by this release. See the
  [Supabase RLS advisory](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public)
  and [function-exposure advisory](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable).

## Production archive reconciliation

These are verified storage counts for the connected Supabase project, not global
NASA completeness claims or counts from a separate local database.

| Measure | Observed |
| --- | ---: |
| Archived sources | 40 |
| Raw records | 9,975 |
| Normalized observations | 9,225 |
| Provenance links | 9,225 |
| Quality reports | 40 |
| Raw rows without normalized links | 750 |

All 750 unlinked raw rows precede 2013. Raw acquisition dates span 2000-12-03 to
2025-12-31; normalized acquisition dates span 2013-01-01 to 2025-12-31. This
matches the earlier import profile's date restriction. Normalizing the earlier
archive and auditing its application coverage remains a separately tracked task.

| Executable check | Threshold | Result | Failure action / owner |
| --- | --- | --- | --- |
| Source SHA-256 versus stored original bytes | 0 mismatches | 0 | Block release, data engineer investigates |
| Declared source rows versus archived raw rows | 0 mismatches | 0 | Block release, data engineer investigates |
| Normalized observation without provenance | 0 | 0 | Block release, backend engineer investigates |
| Provenance link hash versus canonical hash | 0 mismatches | 0 | Block release, backend engineer investigates |
| Repeated canonical record hashes | 0 groups | 0 | Block release, data engineer investigates |

`python scripts/audit_archive.py` runs these checks in a read-only transaction
and includes the sensor/year/month storage matrix. It does not infer clear-sky
observation opportunities, authenticity, or complete months from detections.

## UI baseline for the next batch

Captured with the project's web-uplift evidence CLI against the live five-page
site; artifacts are retained locally under
`reports/pirx-nasa.onrender.com/2026-11-15-foundations/evidence/`.

- Single 390x844 mobile layout samples showed 0 px horizontal overflow on all five
  routes. This does not establish behavior at every viewport or zoom level.
- Dashboard desktop and mobile screenshots were captured. The early mobile capture
  showed a loading state; a settled capture and DOM probe confirmed its heading
  rendered and loading finished. A label probe found all 14 rendered inputs had
  labels or explicit accessible names. No full accessibility compliance is claimed.
- One desktop dashboard HAR sample recorded 47 requests and approximately 2.07 MB
  transferred, with no HTTP error responses in its capture window. The favicon
  transferred approximately 623 KB, Inter approximately 449 KB, map JavaScript
  approximately 292 KB and chart JavaScript approximately 204 KB. These are
  optimization candidates, not a representative field-performance percentile.
- The next visual/performance pass should investigate font/icon delivery and static
  asset caching first, then profile data-dependent loading and interactions.

This is a reconnaissance baseline, not the completed 17-principle web-uplift audit;
no quality score is assigned. Remaining work includes keyboard/screen-reader
journeys, reduced motion/theme states, real interaction performance and memory
profiling, export journeys, and any resulting fixes with before/after evidence.

## Remaining scope

Dedicated least-privilege API/ingestion identities, extension-owned PostGIS exposure,
backup restoration and production rollback rehearsals, credential-rotation evidence,
runtime version pinning, Render HTTP health-path configuration and automatic deploy
delivery require follow-up. Native Render currently selects newer Python/Node
versions than CI's Python 3.12/Node 22, so this batch does not establish identical
toolchain versions across those environments.

The Jordan/Levant candidate models remain scientifically unapproved. No new
observability dataset, independent ground truth, or successful calibration result
is implied by this engineering release.
