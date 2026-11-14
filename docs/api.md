# API contract

Base URL: `http://localhost:8000/api/v1`. OpenAPI and interactive documentation: [Swagger UI](http://localhost:8000/docs). No database credentials are exposed through configuration. The API is read-only; POST endpoints perform queries only.

| Endpoint | Behavior |
| --- | --- |
| `GET /health/live` | Process liveness; no database required |
| `GET /health/ready` | PostGIS and schema revision readiness; 503 on failure |
| `GET /config` | Public capabilities, sensor codes, CRS, limits, science notes |
| `GET /sensors` | Database sensor reference catalog |
| `GET /observations` | GeoJSON point collection with GET filters |
| `POST /observations/query` | GeoJSON point collection, including polygon filtering |
| `GET /observations/{id}` | Original fields, source hash/URL, version, uncertainty, record hash and all linked source copies |
| `POST /analytics/summary` | Counts, known FRP summary and UTC daily counts for the full matching query |
| `GET /sources?limit=50&offset=0` | Source archive metadata; excludes original binary payload |
| `GET /calibration-models/{sha256}` | Registered immutable statistical model artifact and validation scope; candidates are not automatically enabled |
| `GET /quality-reports/{job_id}` | Immutable per-import quality report, including rejected imports |
| `GET /jobs?limit=50` | Most recent processing jobs and output metadata |
| `GET /aggregates/{job_id}?limit=1000&offset=0` | GeoJSON polygons for a successful aggregate job |

## Observation query

GET uses `bbox=west,south,east,north`, `start`, `end`, repeated `sensors`, optional `confidence`, `limit` and `offset` parameters. POST uses the equivalent typed JSON object and additionally supports `polygon`.

```json
{
  "bbox": [34, 29, 40, 34],
  "start": "2024-01-01T00:00:00Z",
  "end": "2025-01-01T00:00:00Z",
  "sensors": ["MODIS_TERRA", "VIIRS_SNPP"],
  "limit": 2000,
  "offset": 0
}
```

For polygon searches, pass a **geometry**, not a Feature or FeatureCollection:

```json
{
  "polygon": {
    "type": "Polygon",
    "coordinates": [[[34, 29], [40, 29], [40, 34], [34, 34], [34, 29]]]
  },
  "sensors": [],
  "limit": 2000
}
```

These coordinates specify a query region only, not observations. Empty `sensors` means all sensors. Confidence accepts `low`, `nominal`, or `high` as native quality-class filters, not a common probability threshold. Timezone-aware timestamps are mandatory, time end is exclusive, and bounds include their boundaries. Valid 2D WGS84 Polygon and MultiPolygon geometries (including holes) are supported, up to 10,000 vertices. Split antimeridian polygons; wrapped bboxes are supported directly.

Observation pages are ordered by acquisition time and observation ID, with default limit 2,000 and hard maximum 5,000. `metadata.has_more` distinguishes a truncated page from a complete result. Offset pagination is stable for an unchanged archive; new imports can shift offsets. Summary queries ignore limit/offset, cover the entire spatial/time selection, and omit unobserved days. Empty archive count is zero, while FRP sums and time extents are null. Database outages are 503 responses, never empty 200 results.

Invalid spatial/time/filter requests return 422. Missing records or unsuccessful aggregate job IDs return 404. Operational errors are sanitized and do not echo connection strings or SQL credentials.

Observation queries now read canonical normalized records introduced by migration `0002_ingestion`. Exact repeated payloads are counted once; original raw copies remain linked. Summary source counts include all raw source files linked to matching normalized observations. Existing aggregate job outputs remain unchanged.
## Historical intelligence

`POST /api/v1/analytics/history` returns calendars, seasonal medians, matched-month
comparisons, descriptive anomalies, grid concentration and source metadata.
`POST /api/v1/analytics/history/export.csv` accepts the same body.
See [the full metric and completeness contract](historical-intelligence.md).
