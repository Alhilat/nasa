# Science and data contract

No fire observations, analytical results or confidence estimates are generated for demonstration. A fresh installation has sensor reference metadata only. Test data are synthetic software fixtures in `tests/`, never a scientific dataset or a production seed.

## Raw inputs and provenance

Operators supply NASA FIRMS CSV exports with an explicit sensor/platform, product version, processing level, public source URL and retrieval timestamp. Each source’s exact bytes and SHA-256 checksum are stored with the original filename. Every parsed field—including unknown columns—is retained as a string in `raw_properties`. Normalized timestamps, coordinates, confidence classes and optional measurements are additional queryable fields; they do not replace original source values.

`source_row` is the one-based CSV data-record number, excluding the header. It is not a byte or physical-line offset (quoted fields may contain newlines). UTF-8 with optional BOM is supported. Missing optional FRP/scan/track fields become null only in the normalized index. Default strict imports abort on invalid fields. Explicit quarantine archives structurally valid raw records while excluding invalid rows from normalization and reporting them. Malformed CSV always rejects the whole file; there is no silent row dropping or imputation.

The hash proves file identity, not NASA authenticity. `authenticity_verified` is false. Preserve source download and citation context. No NASA API key is needed for locally supplied files. Optional API synchronization checks source availability and preserves returned CSV bytes, using a server-only MAP_KEY. See [the ingestion contract](ingestion.md).

## Initial harmonization method: `wgs84-grid-daily-v2`

1. Use archived normalized observations in a required `[start, end)` UTC interval.
2. Assign each point to an angular cell anchored at (−180°, −90°). The grid size must divide 180°, with an allowed range of 0.01°–5°. Default: 0.25°.
3. Use `floor((lon + 180) / size)` and `floor((lat + 90) / size)`, clamping the positive world edges to the last cell.
4. Group by sensor/platform, UTC acquisition day, and cell indices. Sensor identity is never pooled away.
5. Retain detection count, number of known FRP measurements, and sum of known FRP (MW). With no known FRP, the sum is null, not zero. Partial sums must be read with the known-value count.
6. Store grid geometry, input source manifest, algorithm version, time bounds and uncertainty flags against the processing job.

This is structural harmonization, not radiometric or detection-probability calibration. Angular cells are not equal area. Summed FRP across observations is neither energy nor instantaneous regional power. Counts are not unique fire events and must not be interpreted as burned area. Exact repeated full payloads share a normalized record while all raw copies remain. Changed payloads, repeated overpasses and NRT/standard revisions remain distinct; no sensor equivalence is assumed. Analysts must define an overlap/replacement policy before using this archive for an unbiased long-term trend.

## Confidence and uncertainty

MODIS confidence is retained as supplied (native numeric 0–100), with display classes low <30, nominal 30–79, and high ≥80. VIIRS retains `l/n/h` mapped to low/nominal/high. These are quality categories, **not calibrated probabilities**, and their matching class names do not imply cross-sensor equivalence. Nominal 1 km MODIS and 375 m VIIRS resolution is not a measured positional uncertainty. Scan/track dimensions are retained where provided.

Quantitative uncertainty is explicitly null. Per-observation and aggregate JSON flags describe unknown coverage, uncorrected sensor bias, retained overlaps, and unequal cell areas. No uncertainty is invented from pixel size or confidence. Future uncertainty propagation needs product-specific validation and a documented error model.

## Interpretation and deferred analytics

The explorer shows unadjusted daily counts per native sensor and archive filters. Only days with observations appear; missing bins are not filled with zeros. Missing detections can reflect cloud/smoke cover, overpass timing or detection limits. Observation counts alone cannot establish coverage or fire absence.

An experimental classical statistical calibration workflow now evaluates baseline aggregation, seasonality-aware regression and quantile mapping with blocked year/region holdouts. It produces separately versioned candidate estimates and refuses operational calibration when observability, product scope, holdout support or trend stability is inadequate. Physical uncertainty in original observations remains unknown; bootstrap intervals describe only statistical mapping/agreement variability. Historical intelligence now supplies per-sensor seasonal profiles and descriptive anomalies, with explicit month-completeness declarations and prior-year reference periods. See [the historical metric contract](historical-intelligence.md). Forecasting remains unimplemented. See [the full calibration methodology](harmonization-methodology.md).

## Primary sources

- [NASA FIRMS fire alert notes](https://firms.modaps.eosdis.nasa.gov/alerts/notes.php): UTC acquisition times, sensor resolution, confidence caveats and reasons for missed detections.
- [NASA VIIRS Active Fire User Guide](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf): native VIIRS product interpretation.
- [NASA FIRMS active fire data access](https://firms.modaps.eosdis.nasa.gov/content/active_fire/): export access and NRT/standard product replacement lifecycle.

Attribution is retained per source as NASA FIRMS / EOSDIS, with the operator-supplied location and product metadata. This project is an independent challenge implementation, not an official NASA service.
