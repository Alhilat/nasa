# Gemini scientific intelligence

FireScope's dashboard includes **AI Intelligence**, a conversational interface over
the existing historical engine. Gemini chooses declared tools and supplies an
interpretation. Python retrieves data, computes every numeric result, and constructs
the evidence, charts and dataset citations. The existing MODIS/VIIRS calibration
pipeline is never replaced, refitted, or automatically applied by the agent.

## Configuration and startup

The implementation uses the official `google-genai` Python SDK, pinned in
`backend/pyproject.toml` and `requirements.lock`. Follow the main README for the
PostGIS archive and migrations, then install the updated requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
```

Set these server variables in the ignored root `.env` or deployment environment:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODELS=gemini-3.1-flash-lite,gemini-3.5-flash,gemini-4-hydrogen
AI_REQUESTS_PER_MINUTE=8
AI_REQUESTS_PER_DAY=100
AI_CONCURRENT_REQUESTS=2
```

Fill in the key privately. Never use a `VITE_` variable for credentials. A key shared
in chat should be replaced in Google AI Studio and its replacement stored locally.
Restart FastAPI after changing configuration:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The Compose `api` service receives Gemini settings from the environment. No Gemini
key is provided to the frontend build, database, pipeline or migration service.
The default model was checked against the supplied project's available model list;
`GEMINI_MODEL` can select another model supporting function calls and JSON schema,
and `GEMINI_FALLBACK_MODELS` defines an ordered comma-separated or JSON list of fallback
models tried automatically when the primary model fails due to unavailability, quota
exhaustion, or unusable output (credential/permission `401`/`403` errors still fail
immediately without fallback). When a fallback model succeeds, the reply `model` field
reports the model that actually answered and `notices` discloses the fallback.
No model is downloaded or trained. This feature is distinct from custom forecasting
or independently evaluated prediction accuracy, neither of which is implemented.

## Architecture

1. The browser sends a question, the applied map selection, exact UTC date window,
   caller-attested completeness declarations and an optional opaque conversation ID.
2. FastAPI validates the body, selection, provider configuration and request limits.
3. An SDK request forces a declared function call before accepting any factual answer.
   Automatic function execution is disabled. Only the server's allowlist can run.
4. Validated Python tools call the existing historical services and registered model
   metadata. Arguments cannot contain SQL, executable Python, filenames, arbitrary
   URLs or invented region geometry. Queries are read-only.
5. Full model Content and opaque thought signatures/call IDs are retained during the
   bounded function-call loop. Function responses use the API's `user` role.
6. A separate, tool-free Gemini request produces a Pydantic/JSON-schema interpretation.
   Every statement must cite current server-issued evidence IDs. Unknown citations,
   numeric assertions, generated URLs and common unsupported causal/forecast assertions
   are rejected. Numeric prose in English words is also rejected.
7. Actual observations, comparisons, anomaly statistics, charts and citations come
   directly from Python evidence, independently of model prose. Invalid prose or a
   failed final interpretation yields `evidence_only`, with the valid evidence retained.
   Initial provider/authentication/quota errors are explicit sanitized HTTP failures.

The SDK API key is passed only as provider authentication, not as a prompt field.
Prompt text also redacts accidental repetitions of the configured key. Tool output
does not include original NASA file bytes, arbitrary source metadata or credentials.
Questions, selected regions and bounded evidence **are sent to Google Gemini when the
user submits**; the interface states this. Source fields and prior messages remain
untrusted data, never new instructions or permission to execute actions.

Citation/schema/number checks constrain model output; they are not a proof of semantic
truth in unconstrained natural language. Narrative is clearly labelled interpretation,
should be reviewed against the evidence, and cannot establish causation. The code does
not promise a zero hallucination rate or scientifically validated AI prediction accuracy.

## Backend tool registry

| Tool | Evidence and limits |
| --- | --- |
| `get_historical_activity` | Monthly observed counts, partial yearly totals and seasonal profiles, source checksums and charts. No zero filling. |
| `compare_fire_seasons` | Same specified calendar months across requested years, by sensor. Numerical changes require matched complete months and equivalent geometry. Different regions receive descriptive archive counts only, with no count ratio or difference. |
| `detect_activity_anomalies` | Existing Python percentile flags, thresholds, earlier-year medians, unassessed counts and missing-data reasons. No risk predictions or significance claims. |
| `analyze_spatial_hotspots` | Existing angular-cell shares, Herfindahl concentration and up to fifty leading cells. Not physical-area-normalized density or exposure correction. |
| `get_harmonization_metadata` | Registered versions, methods, scope/status and original held-out evaluation metadata. Sensor-reference agreement is not physical fire truth. No model application or operational approval. |
| `get_environmental_conditions` | Explicit **unavailable** result: no environmental dataset is connected. No temperature, vegetation, soil moisture or weather is estimated. |
| `generate_activity_report` | Historical evidence, valid adjacent-year comparisons, anomalies, spatial concentration, calibration metadata and environmental-data availability. All numeric content remains Python evidence. |

Named-region support is deliberately constrained to the current map selection, a
labelled Jordan study envelope and the existing four `JOR_*` study blocks. The block
GeoJSON is packaged with the backend and its SHA-256 is cited. These are study regions,
not official national boundaries. Unknown geographic names require a map selection or
an additional curated region; the model cannot invent coordinates or geocode silently.

Scope tools accept `region_id`, optional start/end years, sensors, or paired inclusive
`start_date` / `end_date` values. Explicit dates must agree with any explicit years and
cannot be in the future. Exact-window retrieval uses the existing observation filters,
then the same Python historical engine. Partial months lose completeness declarations;
fully outside months are excluded from charts. Annual archive totals may be partial.
Changes of region clear the original area's completeness declarations. The caller's
selected date window is inherited unless the question explicitly selects other years
or dates. Comparison tools disclose their exact requested season and geography.

Historical references, confidence limitations and definitions remain governed by
[the historical intelligence contract](historical-intelligence.md). A thermal hotspot
is a detection, not a unique wildfire, burned area, ignition probability, or forecast.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/ai/status` | Public configured flag, model, fallback models, tool names, curated regions and usage/privacy notes; never a key. Does not require PostGIS. |
| `POST /api/v1/ai/chat` | Tool-grounded conversation turn with validated structured interpretation and Python evidence. |
| `POST /api/v1/ai/reports` | Same body; first tool selection is constrained to `generate_activity_report`. |
| `POST /api/v1/ai/reports/export` | Export an existing conversation-owned report as Markdown or JSON. Accepts only conversation ID, report ID and format, not client-generated findings. |
| `POST /api/v1/ai/conversations/reset` | Forget the capability's current conversation and reports. |

Example chat body:

```json
{
  "message": "Explain seasonal activity and data limitations for this selection.",
  "context": {
    "start_year": 2013,
    "end_year": 2025,
    "bbox": [34, 29, 40, 34],
    "sensors": ["MODIS_TERRA", "VIIRS_SNPP"],
    "complete_months": []
  },
  "date_window": {"start_date": "2013-01-01", "end_date": "2025-12-31"},
  "refresh": false
}
```

A reply includes `conversation_id`, `report_id`, model and UTC creation time, structured
interpretation or null, evidence records, tool-call audit, notices and `forecasting:false`.
Evidence contains the resolved query/period, analysis IDs, source metadata, immutable
numeric facts, charts, limitations, retrieval time and cache-hit status. Evidence IDs
are content hashes, not externally verified proofs of authenticity. Source lists are
limited to a hundred entries and fact lists to a hundred twenty, with truncation flags.
The displayed model view is smaller; missing/omitted values are never inferred.

Markdown reports include executive summary, historical observations, statistical
comparisons, anomalies, supporting evidence, data limitations and monitoring
recommendations. An empty section says no assessed result was returned, rather than
claiming no anomalies or complete coverage. Only the latest two reports per conversation
are retained for server export; expired reports require a new analysis. Scientific SVG
chart exports include evidence scope, analysis IDs and source metadata.

## Resource and deployment boundaries

- AI POST bodies are capped at 64 KiB before JSON decoding, including streamed bodies.
- Questions are capped at three thousand characters. Each analytical selection is
  capped at fifty thousand normalized observations and the historical engine's
  maximum fifty-year span. Oversized queries produce unavailable evidence, not truncation.
- At most six tool invocations across three planning rounds, plus a final structured
  interpretation request. SDK automatic function calling/retries are disabled.
- Provider HTTP timeout is twenty seconds per call; the loop has a soft seventy-five
  second budget checked between rounds. An already running provider or database call
  may finish after that budget. Aborting a browser request does not guarantee cancellation
  of work already sent to Google.
- Concurrency, per-peer minute limits and a process-wide UTC daily allowance are bounded.
  Rate/quota responses use 429 and `Retry-After`. Direct peer identity is used; arbitrary
  forwarded headers cannot manufacture fresh allowances.
- Analytical snapshots are cached for thirty seconds, at most sixteen entries/eight
  serialized megabytes, with a two-megabyte per-entry cap. `refresh:true` bypasses shared
  cache. A request memo avoids repeated calculation of the same scope. Cache identity
  includes geometry, dates, sensors, confidence and completeness declarations.
- Gemini receives compact geometry fingerprints and at most sixteen thousand characters
  per evidence view; final interpretation input is capped. Full evidence remains server-side
  and in the reply. Four recent question/interpretation summaries are retained, not full
  prior tool payloads or client-provided assistant history. Map/date changes start a new
  conversation to prevent stale evidence from being reused as current observations.
- Conversations expire after thirty idle minutes, maximum sixty-four per process. IDs
  are unguessable possession capabilities. Keep them private. Reports use no-store headers;
  conversation IDs and export identities are sent in POST bodies rather than URL paths.
- This repository's normal services are bound to loopback. This is a single-archive,
  single-process session/cache implementation, not a multi-tenant authentication system.
  For public or multi-worker hosting, add authenticated access and shared session/quota
  storage at the deployment boundary. Process restarts clear ephemeral sessions and quotas.

## Verification and official references

Unit tests use the existing explicitly synthetic software fixture and a mocked Gemini
provider. They exercise numerical provenance, same-month comparisons, missing coverage,
exact-day windows, prompt/key isolation, malformed tools, numeric/citation rejection,
thought-signature/call-ID preservation, report ownership, body/rate/concurrency limits,
session changes, cache freshness, frontend context changes and export transport.

An opt-in manual live check was performed with the configured key: Google's model list
accepted it, and Gemini selected `get_environmental_conditions`, consumed its explicit
unavailable result, then returned a validated structured interpretation. This verifies
the live SDK/function/JSON flow; it does **not** claim that environmental observations
exist or that unavailable local PostGIS measurements were analyzed.

Official implementation references:
[Google GenAI Python SDK](https://googleapis.github.io/python-genai/),
[Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling),
[structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), and
[model catalog](https://ai.google.dev/gemini-api/docs/models).
