"""Lossless FIRMS validation, independent of persistence and network access."""
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from firescope_pipeline.selection import Selection

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 250000
ALGORITHM_VERSION = "firms-csv-v2"
PLATFORMS = {
    "MODIS_TERRA": {"terra", "t"}, "MODIS_AQUA": {"aqua", "a"},
    "VIIRS_SNPP": {"n", "s-npp", "snpp", "suomi npp"},
    "VIIRS_NOAA20": {"1", "noaa-20", "noaa20"},
    "VIIRS_NOAA21": {"2", "noaa-21", "noaa21"},
}
SOURCE_SENSORS = ["MODIS", *PLATFORMS]


def number(value: str, name: str, *, optional=False, positive=False) -> float | None:
    if not value.strip() and optional:
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


def native_confidence(value: str, instrument: str) -> str:
    cleaned = value.strip().lower()
    if instrument == "VIIRS":
        if cleaned not in {"l", "n", "h"}:
            raise ValueError("VIIRS confidence must be l, n or h")
        return {"l": "low", "n": "nominal", "h": "high"}[cleaned]
    result = number(cleaned, "MODIS confidence")
    if not 0 <= result <= 100:
        raise ValueError("MODIS confidence must be in [0,100]")
    return "low" if result < 30 else "nominal" if result < 80 else "high"


def resolve_sensor(raw: dict, selected: str) -> str:
    candidates = [key for key, aliases in PLATFORMS.items()
                  if raw["satellite"].strip().lower() in aliases
                  and (key.startswith("MODIS_") if selected == "MODIS" else key == selected)]
    if len(candidates) != 1:
        raise ValueError("satellite does not match the selected sensor/platform")
    sensor = candidates[0]
    if raw.get("instrument", sensor.split("_")[0]).strip().upper() != sensor.split("_")[0]:
        raise ValueError("instrument does not match the selected sensor")
    return sensor


def normalize_row(raw: dict, selected: str, product_version: str, row_number: int) -> dict:
    sensor = resolve_sensor(raw, selected)
    instrument = sensor.split("_")[0]
    if product_version == "native":
        if not raw.get("version", "").strip():
            raise ValueError("version is required when using native product versions")
    elif raw.get("version") and raw["version"].strip() != product_version:
        raise ValueError("version does not match --product-version; split mixed products")
    lat, lon = number(raw["latitude"], "latitude"), number(raw["longitude"], "longitude")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordinates must be WGS84 longitude/latitude")
    time = raw["acq_time"].strip()
    if not re.fullmatch(r"\d{1,4}", time):
        raise ValueError("acq_time must be HHMM digits")
    time = time.zfill(4)
    if int(time[:2]) > 23 or int(time[2:]) > 59:
        raise ValueError("acq_time hour/minute is out of range")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw["acq_date"]):
        raise ValueError("acq_date must be YYYY-MM-DD")
    try:
        acquired = datetime.strptime(raw["acq_date"] + time, "%Y-%m-%d%H%M").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("acq_date is not a valid calendar date") from exc
    frp = number(raw.get("frp", ""), "frp", optional=True)
    if frp is not None and frp < 0:
        raise ValueError("frp must be nonnegative; undocumented sentinels are rejected")
    daynight = raw.get("daynight", "").strip().upper() or None
    if daynight not in {None, "D", "N"}:
        raise ValueError("daynight must be D, N or blank")
    for field in ("brightness", "bright_t31", "bright_ti4", "bright_ti5"):
        if field in raw:
            number(raw[field], field, optional=True, positive=True)
    return {
        "source_row": row_number, "sensor_code": sensor, "acquired_at": acquired,
        "latitude": lat, "longitude": lon, "frp_mw": frp,
        "confidence_native": raw["confidence"],
        "confidence_class": native_confidence(raw["confidence"], instrument),
        "daynight": daynight,
        "scan_km": number(raw.get("scan", ""), "scan", optional=True, positive=True),
        "track_km": number(raw.get("track", ""), "track", optional=True, positive=True),
        "uncertainty": {"quantitative_uncertainty": None, "confidence_is_probability": False,
                        "nominal_resolution_m": 1000 if instrument == "MODIS" else 375,
                        "resolution_is_geolocation_error": False,
                        "flags": ["coverage_unknown", "sensor_bias_uncorrected"]},
    }


@dataclass
class ParsedBatch:
    raw: list[dict]
    selected: list[dict]
    report: dict


class IngestionRejected(ValueError):
    def __init__(self, report: dict):
        self.report = {**report, "status": "rejected", "normalized_inserted": 0}
        first = report.get("issue_samples", [{}])[0]
        super().__init__(f"Data row {first.get('source_row', '?')}: "
                         f"{first.get('message', 'CSV rejected')}")


def inspect_csv(content: bytes, sensor_code: str, product_version: str,
                selection: Selection | None = None, processing_level: str | None = None) -> ParsedBatch:
    if sensor_code not in SOURCE_SENSORS or not product_version.strip():
        raise ValueError("Supported sensor and nonempty product version are required")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("CSV exceeds 50 MiB; split the source file")
    if b"\0" in content:
        raise ValueError("CSV contains NUL bytes")
    decoded = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(decoded), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise ValueError("CSV is empty or malformed; a CSV header is required") from exc
    if len(set(header)) != len(header) or any(not x or x.strip() != x for x in header):
        raise ValueError("CSV headers must be unique, nonempty and unpadded")
    required = {"latitude", "longitude", "acq_date", "acq_time", "confidence", "satellite"}
    if required - set(header):
        raise ValueError(f"Missing columns: {', '.join(sorted(required - set(header)))}")
    selection = selection or Selection()
    raw_records, selected, issues = [], [], []
    invalid, excluded, missing_frp = 0, 0, 0
    issue_counts, counts, fingerprints, candidates = Counter(), Counter(), Counter(), Counter()
    versions = Counter()
    try:
        for source_row, values in enumerate(reader, 1):
            if source_row > MAX_ROWS:
                raise ValueError("CSV exceeds 250,000 rows; split the source file")
            if len(values) != len(header):
                raise ValueError(f"Data row {source_row}: column count does not match header")
            raw = dict(zip(header, values, strict=True))
            if raw.get("version"):
                versions[raw["version"]] += 1
            record = {"source_row": source_row, "sensor_code": None, "raw_properties": raw}
            raw_records.append(record)
            try:
                normalized = normalize_row(raw, sensor_code, product_version, source_row)
                if processing_level == "standard" and re.search(
                    r"(?:NRT|URT|RT)$", raw.get("version", product_version).strip().upper(),
                ):
                    raise ValueError("Near-real-time version conflicts with standard processing level")
                record["sensor_code"] = normalized["sensor_code"]
            except ValueError as exc:
                invalid += 1
                issue_counts[str(exc)] += 1
                if len(issues) < 100:
                    issues.append({"source_row": source_row, "message": str(exc)})
                continue
            if not selection.includes(normalized):
                excluded += 1
                continue
            selected.append(normalized)
            counts[normalized["sensor_code"]] += 1
            missing_frp += normalized["frp_mw"] is None
            fingerprints[json.dumps([normalized["sensor_code"], raw], sort_keys=True)] += 1
            candidates[(normalized["sensor_code"], normalized["acquired_at"],
                        normalized["latitude"], normalized["longitude"])] += 1
    except csv.Error as exc:
        raise ValueError("Malformed CSV quoting") from exc
    report = {
        "report_version": "firms-quality-v1", "parser_version": ALGORITHM_VERSION,
        "source_sha256": checksum(content), "source_rows": len(raw_records),
        "valid_rows": len(raw_records) - invalid, "invalid_rows": invalid,
        "excluded_rows": excluded, "selected_rows": len(selected),
        "within_file_exact_duplicates": sum(n - 1 for n in fingerprints.values()),
        "within_file_same_sensor_time_position_repeats": sum(n - 1 for n in candidates.values()),
        "selected_missing_frp": missing_frp, "by_sensor": dict(counts),
        "issue_counts": dict(issue_counts), "issue_samples": issues,
        "issue_samples_truncated": invalid > len(issues),
        "filters": selection.as_dict(), "coverage_known": False,
        "observed_product_versions": dict(versions),
        "first_selected_acquisition": min((r["acquired_at"] for r in selected), default=None),
        "last_selected_acquisition": max((r["acquired_at"] for r in selected), default=None),
        "quantitative_uncertainty": None,
        "status": "validation_failed" if invalid else "validated",
    }
    for name in ("first_selected_acquisition", "last_selected_acquisition"):
        if report[name] is not None:
            report[name] = report[name].isoformat()
    return ParsedBatch(raw_records, selected, report)


def parse_csv(content: bytes, sensor_code: str, product_version: str) -> list[dict]:
    """Compatibility strict parser; imports use inspect_csv with explicit reports."""
    batch = inspect_csv(content, sensor_code, product_version)
    if not batch.raw:
        raise ValueError("CSV has no observations")
    if batch.report["invalid_rows"]:
        raise IngestionRejected(batch.report)
    return [{**row, "raw_properties": batch.raw[row["source_row"] - 1]["raw_properties"]}
            for row in batch.selected]


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
