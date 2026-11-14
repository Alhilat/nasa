# Gemini intelligence verification

Verified on 2026-11-14.

- Official SDK: `google-genai==3.3.0`; `pip check` reported no broken dependencies.
- Python suite: **197 passed, 13 skipped**. PostGIS integration tests require
  `TEST_DATABASE_URL`; no live archive measurements were invented for those tests.
- Frontend suite: **29 passed**, including chat transport, region/date context changes,
  evidence display, reports, exports, missing-provider and quota/error states.
- Production TypeScript/Vite build passed. Existing MapLibre/ECharts large-chunk
  warnings remain; these are warnings, not build failures.
- Targeted Ruff and whitespace checks passed.
- Live provider verification accepted the configured key and enumerated available
  models. A real Gemini function-calling round selected `get_environmental_conditions`,
  received explicit unavailability, then returned a validated structured interpretation.
  The final live check also preserved the exact inclusive UTC window
  `2025-01-01` to `2025-01-31` in the returned evidence scope.
- Python numerical verification uses the existing explicitly synthetic fixture:
  January counts of 1, 2, 3 and 8; the earlier-year median is 2 and upper percentile
  threshold 2.9. Matched complete January counts from 2013 to 2016 change by 700%.
  These are software assertions, not findings about NASA observations.
- Security/grounding tests reject unknown tools/regions, path and extra-argument
  injection, unsupported numeric/causal prose and fabricated citations. They check
  model thought-signature/call-ID preservation, owned exports, body/rate/concurrency
  limits, cache freshness, partial-month handling and accidental key repetition.
- The configured key was scanned against tracked/new source and production output:
  no matches. Root `.env` is Git-ignored. No credential is present in this report.

Environmental data remain unconnected. Local PostGIS readiness was unavailable, so
the live provider test verified interpretation of data availability, not analysis of
the Jordan archive. AI prose remains interpretation and requires scientific review;
schema/citation checks are not a guarantee of semantic truth.

See [setup, API, limits and scientific contract](../gemini-intelligence.md).
