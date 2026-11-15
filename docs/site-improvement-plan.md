# PIRX full-site improvement plan

Planning baseline: 2026-11-15. Scope: the Render website, FastAPI, Supabase archive,
ingestion, scientific comparisons, exports, and AI interpretation.

Implementation update: the first foundations batch is deployed and verified.
See [the production evidence and remaining scope](site-foundations-verification.md).
This completes the artifact guard, combined-site CI/smoke checks, application-table
access hardening, and initial archive/UI reconnaissance. The full UX audit,
operational recovery drills, remaining security work and scientific research are
still tracked below.

This is an implementation roadmap, not a completed UX audit or a scientific
validation certificate. No application or production configuration changes are
authorized by this document alone.

## Current baseline and intended outcome

- All five public routes returned HTTP 200 during this planning session. A browser
  DOM capture of the live homepage rendered `PIRX · Intelligence dashboard`.
  Successful page responses do not prove every interactive feature works.
- Existing capabilities include region drawing, observation inspection, historical
  calendars, provenance, downloadable evidence, accessible chart alternatives,
  and a tool-backed AI assistant. Improve these rather than rebuilding them.
- The most recent verification in this chat passed 324 backend tests and 103
  frontend tests; 18 database integration tests were skipped locally. CI already
  provisions a disposable PostGIS database. Verify its current results at release.
- Existing Jordan and Levant calibration candidates remain rejected for operational
  use. See [validation review](harmonization-validation-review.md).
- Earlier Supabase advisories reported disabled RLS on public tables. Recheck
  current grants, exposed schemas, views, functions, and policies before changing
  access. Documentation and local data totals may differ from deployed data.

Target outcome: users can choose an area and period, understand what was actually
observed, compare eligible history, inspect the evidence, and export reproducible
results. The site must distinguish raw detections, experimental estimates,
unsupported comparisons, missing observations, and verified zero detections.

## Delivery order

| Phase | Priority | Main owner | Dependency | Completion evidence |
| --- | --- | --- | --- | --- |
| 1. Reliable releases | P0 | Application/platform engineer | Render access | Production smoke checks, build checks, rollback rehearsal |
| 2. Protected and auditable data | P0 | Backend/data engineer | Confirm access model | Permission tests, archive reconciliation, successful restore |
| 3. Consistent user journeys | P1 | Frontend engineer/designer | Working release | Browser journey tests and accessibility evidence on all pages |
| 4. Scientific validation | P1 research track | Domain scientist/data engineer | Observability data and locked protocol | Reproducible held-out evaluation and explicit decision |
| 5. Speed, resilience, and AI quality | P1 | Frontend/backend engineers | Measured baseline and realistic archive | Performance, failure-recovery, and AI evaluation results |
| 6. Release and maintenance | P1 | Release owner | Product release gates | Release evidence, monitoring, runbooks |

Phases 1–2 come first. Phases 3 and 4 can proceed in parallel after their own
dependencies are met. Ship a useful exploratory release without waiting for
calibration acceptance; retain separate sensor series whenever validation fails.

## 1. Make releases dependable

- Use the existing service serving frontend and API together as the initial
  production path. Record whether Render uses Python or Docker and make the
  documented settings match that path. Reconcile the optional two-service
  Blueprint so it cannot silently reintroduce inconsistent API URLs.
- Verify the native build command builds the frontend and that the deployed
  artifact includes `frontend/dist/index.html` and every referenced asset.
- Fail the production build if required frontend artifacts are missing. Preserve
  deliberate API-only local operation as a separate supported mode.
- Add an end-to-end release check for `/`, every direct page route, assets,
  basemap, API readiness, and a real read-only archive query. Test HEAD requests
  and page refreshes as well as navigation from the homepage.
- Expose a non-secret build/version identifier; report frontend and API status
  separately. Rehearse redeploy and application rollback without reversing data
  migrations or deleting source archives.

Done when: a clean checkout builds reproducibly, CI exercises the combined
artifact, and the deployed version passes those checks.

## 2. Protect Supabase and establish archive completeness

- Confirm the intended architecture: browsers call FastAPI; direct Supabase table
  access is unnecessary unless a particular feature explicitly needs it.
- Separate migration, ingestion, and read-only API database privileges. Review
  grants and RLS for exposed application tables, views, and callable functions.
  Develop and test the policies against those roles before applying them. Treat
  extension-owned PostGIS objects separately; avoid blanket schema alterations.
- Verify that previously exposed credentials have been rotated and updated in
  local/Render secret storage. Keep secret detection in the release checks.
- Reconcile source manifests, hashes, quality reports, checkpoints, canonical
  rows, dates, sensor/platform identity, and processing versions with Supabase.
  Do not infer completeness from successful imports or row totals alone.
- Investigate pre-2013 normalization exclusions and expand application history
  only after an intentional scope change, idempotent reprocessing, and date-range
  verification. Preserve all original source bytes and provenance links.
- Publish a coverage matrix by region, sensor, month, and product version. Show
  archive coverage separately from satellite observation opportunity.
- Define backup retention, recovery point/time targets, and a tested restore
  process including archived source bytes. Keep test imports out of production.
- Add request/query budgets and appropriate rate limits. Profile expensive queries
  before adding indexes or moving source bytes to object storage.

Done when: unauthorized reads/writes are denied, legitimate API/ingestion workflows
still work, archive totals reconcile, and a backup restores successfully.

## 3. Improve every page around complete user tasks

| Surface | Improvements to evaluate and implement | Acceptance journey |
| --- | --- | --- |
| Dashboard `/` | Clear area/date/sensor summary; consistent units; coverage and uncertainty next to headline numbers; primary filters above advanced controls | Choose region and period, apply filters, understand the result and limitations |
| Explorer `/explorer` | Map/table selection synchronization; visible result cap and paging; reliable inspector; preserve filters through navigation; shared links | Draw a polygon, inspect a detection, trace its source, export the intended records |
| History `/history` | Explicit baseline years; comparable sensors/products; missing versus zero states; separate native/experimental/approved views; accessible trend tables | Compare eligible periods and explain why a comparison is assessed or withheld |
| Sources `/sources` | Search/filter source files and jobs; understandable import status; checksums/citations; separate archived validation studies from live results | Trace a plotted value to its source and processing evidence |
| Methodology `/methodology` | Plain-language definitions; limits close to relevant claims; versioned methods; validation decisions and NASA attribution | Explain what a hotspot, confidence class, FRP value, and anomaly do and do not mean |
| AI assistant | Evidence links, applied-region context, clear provider/cost/failure states, preserved evidence when interpretation fails | Ask a supported question, inspect its evidence, export a reproducible answer |

Across pages: use one region/date/filter model, deliberate pending-versus-applied
states, shareable query state, consistent loading/empty/error/retry patterns, and
explicit export scope. Decide whether full-query exports require a bounded server
job; never label a visible page download as the complete dataset.

Perform the planned web-uplift audit on all five page archetypes and the AI/inspect
journeys. Use the configured guidance catalog and evidence CLI for desktop and
360/390 px mobile, keyboard operation, reduced motion, and applicable theme modes.
Capture screenshots, DOM/layout, network and performance summaries; run axe and
manual keyboard/screen-reader checks. Repeat map and route interactions to check
memory cleanup. Preserve reports and before/after evidence; do not invent scores.
Evaluate all skill principles, documenting justified contextual exclusions.

Done when: the journeys work on desktop and mobile, filters survive navigation,
errors are recoverable, chart data remains available without color or a pointer,
and no known critical accessibility issue blocks a core task. Arabic/RTL support
is a product decision; if selected, localize labels, layout, dates and number
formatting while retaining explicit UTC acquisition semantics.

## 4. Establish scientifically defensible comparisons

- Retain the existing rejected studies as reproducible baselines. Define the
  intended metric, geographic scope, platforms, day/night strata and product
  versions before selecting or fitting the next candidate.
- Acquire paired observation opportunity information: swath/geolocation, fire
  masks, cloud/quality data, viewing geometry and acquisition time differences.
  Include valid non-detection opportunities. Hotspot-only CSVs are insufficient
  for establishing an observation denominator.
- Use only periods where both products actually overlap for cross-sensor tests;
  pre-VIIRS MODIS years remain valuable native-sensor history.
- Add independent regions and years, with representative low/high activity and
  seasons. Lock training/selection/test splits and acceptance thresholds before
  looking at the new held-out results. Keep retrospective checks labeled.
- Compare to simple baselines, report bias/MAE/RMSE and support, and test seasonal
  profiles, matched-calendar trends, geographic transfer, grid choices and product
  transitions. Quantify uncertainty according to its actual statistical meaning.
- Where appropriate, evaluate against independent reference evidence compatible
  with the target metric. MODIS agreement is not proof of physical fire truth;
  burned area is not interchangeable with a hotspot count.
- Publish an accept/reject decision tied to a versioned model and approved scope.
  Run unsupported/extrapolated selections through the existing withholding logic.
  Do not force acceptance to meet a release date.

Done when: a reproducible review supports acceptance for a specific scope, or
documents why native series must remain separate. Either decision is a valid
research deliverable; reduced average error alone is insufficient.

## 5. Improve performance, resilience and interpretation

- Measure warm and cold production behavior separately. Establish device/network
  and archive-size baselines before changing map, chart or API rendering.
- Proposed field targets: LCP <= 2.5 s, INP <= 200 ms and CLS <= 0.1 at the 75th
  percentile for eligible visits. Set endpoint-specific latency and resource
  budgets after profiling realistic regions/date ranges.
- Inspect MapLibre/ECharts chunks, lazy-load expensive views, bound map features,
  and avoid repeated identical requests. Consider deferred rendering only for
  measured below-fold sections, with intrinsic sizing and keyboard verification.
- Cache suitable immutable assets and bounded analytical results using keys that
  include applied filters, archive revision and method/model version. Cancel stale
  requests and test switching filters while requests are in flight.
- Test provider timeouts, quota limits, missing map tiles, unavailable database,
  interrupted network and malformed responses. Explain stale data explicitly.
- Extend the existing AI guardrails with an evaluation set for missing coverage,
  unsupported sensor comparisons, ambiguous dates, provider failures and prompt
  injection. Measure citation validity and evidence consistency; retain bounded
  server tools and evidence-only fallback. Do not add forecasting claims by default.
- Review third-party network requests, security headers, privacy disclosures,
  indexing intent, metadata, and whether methodology content needs prerendering.

Done when: recorded comparisons show improvement without changing scientific
results, failure recovery preserves user context, and AI evaluations pass the
declared evidence rules.

## 6. Release gates and ongoing ownership

Release an exploratory product only when the production smoke tests, core browser
journeys, database permission checks, reproducible exports, backup restore, and
applicable CI checks pass. Display experimental and unknown states accurately.

Release a scientifically approved cross-sensor feature only after phase 4's
independent gates pass and the exact training aggregation/units are implemented
in the consuming application. A software test pass cannot approve a model.

Assign owners for deployment incidents, archive imports, data-quality exceptions,
security updates and scientific model review. Maintain alerts for availability,
API errors, import failures, connection exhaustion and stale archives. Review
dependencies and NASA product/provider changes on a defined maintenance cadence.

## Effort and first implementation batch

Planning estimates for one engineer, subject to the evidence baseline: phases 1–2
roughly 3–6 engineering days, page/UX improvements 5–10 days, and performance/AI/
release hardening 4–8 days. Research requires a domain reviewer and a separate
estimate after observation data access, licensing and processing effort are known;
additional weeks may be required, with no guaranteed calibration acceptance date.

First batch: verify Render's reproducible build and artifact guard; add production
smoke checks; reconcile Supabase permissions and archive coverage; then execute
the five-page UX/accessibility audit and rank its evidence-backed improvements.

## Evidence and planning references

- Source review: `docs/architecture.md`, `docs/operations.md`, `docs/science.md`,
  `docs/accessibility.md`, `docs/gemini-intelligence.md`,
  `docs/harmonization-validation-review.md`, `frontend/src/App.tsx`, and CI.
- Live recon: web-uplift DOM primitive on the homepage and read-only HTTP requests
  to all five routes. DOM evidence is under ignored `reports/site-plan-baseline/`.
- Modern Web Guidance catalog `0.0.172`: searched responsive/accessibility guidance;
  retrieved `defer-rendering-heavy-content` for the conditional rendering proposal.
  Future audit findings require their own per-principle guidance and evidence.
- No full visual/accessibility/performance audit or new Supabase security audit
  was completed for this plan. No defects or quality scores are asserted for
  untested journeys; those are explicit verification tasks above.
