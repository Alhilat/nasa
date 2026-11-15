# Component restoration report

## Recovery sources

The audit covered all seven Git revisions from `5f71404` through `8075073`, the complete frontend source tree, backend services, ingestion code, tests, configuration, infrastructure and analytical documentation. Revision `362d985` supplies the feature-complete restoration reference. Later scientific fields, archive completeness handling, detection-context checks and date controls remain present.

The local staging archive was inspected as an additional source. The older `h/h` directory contains configuration files. An internal checklist and before-edit source snapshots were recorded before restoration changes under the ignored `reports/restoration-audit` directory.

## Identified and recovered elements

| Area | Recovered elements |
| --- | --- |
| Navigation | Observation explorer link, lazy-loaded page and functional `/explorer` route. All five existing destinations are accessible. |
| Application shell | Earth observation descriptor, workspace and constellation labels, scientific approach card and link, version/research row, historical-observation badge, FS mark and complete scientific footer. The current PIRX logo and name remain the visual brand. |
| Dashboard visibility | Disconnected and empty archives now retain the complete dashboard after initial loading. Archive-derived dates remain in use when available. Recovered 2013–2025 filter defaults are explicitly labelled when actual archive dates are unavailable. |
| Summary cards | Archived detections, common-grid activity, original source files and summed observed FRP with known-value count and scientific caveats. Missing values display as unknown. |
| Dashboard exports | Exact-selection detection CSV, monthly calendar CSV and full analysis JSON, with progress and error handling. Existing anomaly-panel exports remain available. |
| Explorer | Original GeoJSON export, displayed-page/query/source metadata, scientific explanation card, daily chart and accessible table, plus original editorial headings and context. Current query handoff and filtering behavior remain available. |
| Chart export | Original SVG toolbar, scientific title and embedded analysis/source metadata. Current ECharts initialization, axes, series mapping, missing-value behavior and rendering are byte-identical to the pre-restoration implementation. |
| Map tools | Original rectangle and polygon drawing, finish/cancel/Escape, map-extent selection, clear selection and PNG export with attribution and scientific scope. Their restoration was explicitly approved in the user's follow-up. |
| AI Intelligence | Markdown report and JSON evidence downloads, dataset source links, scientific evidence headings, welcome explanation, environmental-investigation prompt and privacy/scientific caveats. Current conversation cancellation, selected date context and citation expansion remain available. The supporting-evidence disclosure remains collapsible. |
| Observation details | Original native sensor code and full ISO UTC acquisition timestamp, alongside the current human-readable facts, nearby-detection checks, source identifiers, raw fields and uncertainty metadata. |
| History | Original editorial header and export descriptions, plus CSV progress/error handling. Current harmonized-series, baseline, missing-data, yearly calendar, seasonal-profile and spatial-concentration fields remain present. |
| Methods and sources | Original method/version context, future-work limitations and ingestion/startup guidance, alongside the existing documentary satellite image, references and updated scientific explanations. |
| Responsive content | Recovered sidebar and science cards use the approved identity. The scientific explanation card remains visible on mobile. Drawing controls use a compact mobile grid. |

## Visual identity

Recovered elements use the existing ivory/white editorial surfaces, navy analytical surfaces, blue navigation and actions, orange observation accents, thin borders and restrained corner radii. Space Grotesk, Inter and IBM Plex Mono retain their heading, interface and technical-data roles. Alert red remains reserved for scientifically established critical severity.

## Integrity checks

- Compared 68 protected source files with hashes captured at the start of this task. The authorized drawing restoration changes `RegionMap.tsx`. Backend services, ingestion code, configuration, basemap implementation, the Explorer map and existing chart data components match their starting hashes.
- The observation-layer definition in `RegionMap` is unchanged. Existing observation markers, source updates, coordinates, selection inspection, basemap sources, retries and framing remain intact. The original selection-vertex preview is restored for drawing.
- The rendering effect in `ScientificChart` matches its starting source exactly. The recovered export surrounds that implementation.
- Existing datasets and analytical outputs were preserved. Statistical calculations, calibration and other scientific algorithms were preserved.

## Verification

- Production TypeScript and Vite build completed successfully.
- All 64 frontend tests passed. Regression coverage includes five-route navigation, disconnected/empty dashboards, the recovered cards, CSV/GeoJSON/SVG/report export actions, source metadata, date/confidence/spatial filters, drawing, map bounds, cancellation, detection selection and PNG attribution/scope generation.
- All 233 runnable Python tests passed. Fifteen PostGIS integration tests require `TEST_DATABASE_URL` and were skipped in this environment.
- Existing English-number assertions were made locale-aware, and the basemap test explicitly isolates its style setting. Those changes make the tests reproducible on the host's Arabic-Jordan locale and with its custom map style.
- Browser review exercised all five routes, mobile navigation, map drawing through application of the selected polygon, map-extent transfer to Explorer filters, map reset/clear, the expanded history form and backend-error handling. Desktop and 390 px mobile layouts were checked. No JavaScript warnings or errors were captured in the reviewed flows.

## Verification limits

All identified components and handlers were recoverable from source. The local FastAPI/PostGIS service was offline during browser review, so real-data charts, API exports and Gemini responses require further live verification with that service running. Software fixtures are confined to tests.

PNG generation and the download handler passed automated tests. The preview browser did not expose a download-completion event after the PNG button was clicked, so actual file saving in that browser remains unconfirmed.
