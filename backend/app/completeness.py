"""Reproducible archive-completeness auditing by area, sensor, and month from source evidence.

Archive completeness records whether all FIRMS records from an authoritative source stream
for a specific spatial selection, sensor, and full UTC calendar month have been strictly
validated and imported into the local archive. It is always distinct from satellite
observation coverage (swath, cloud, smoke, or detection sensitivity), which remains unknown
without an independent cell-day observability dataset.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from shapely.geometry import box, shape
from shapely.ops import unary_union

AUDIT_VERSION = "archive-completeness-v2"

SENSOR_AVAILABILITY: dict[str, dict[str, str | None]] = {
    "MODIS_TERRA": {
        "operational_start": "2000-11-01",
        "first_full_month": "2000-11",
        "partial_start_month": None,
        "family": "MODIS",
    },
    "MODIS_AQUA": {
        "operational_start": "2002-07-04",
        "first_full_month": "2002-08",
        "partial_start_month": "2002-07",
        "family": "MODIS",
    },
    "VIIRS_SNPP": {
        "operational_start": "2012-01-20",
        "first_full_month": "2012-02",
        "partial_start_month": "2012-01",
        "family": "VIIRS_SNPP",
    },
    "VIIRS_NOAA20": {
        "operational_start": "2018-01-01",
        "first_full_month": "2018-01",
        "partial_start_month": None,
        "family": "VIIRS_NOAA20",
    },
    "VIIRS_NOAA21": {
        "operational_start": "2024-01-17",
        "first_full_month": "2024-02",
        "partial_start_month": "2024-01",
        "family": "VIIRS_NOAA21",
    },
}

COUNTRY_URL_RE = re.compile(
    r"^https://firms\.modaps\.eosdis\.nasa\.gov/data/country/"
    r"(?P<product>modis|viirs-snpp|viirs-noaa20|viirs-noaa21)/"
    r"(?P<year>\d{4})/"
    r"(?P=product)_(?P=year)_(?P<country>[A-Za-z_]+)\.csv$"
)
PRODUCT_SENSORS: dict[str, tuple[str, ...]] = {
    "modis": ("MODIS_TERRA", "MODIS_AQUA"),
    "viirs-snpp": ("VIIRS_SNPP",),
    "viirs-noaa20": ("VIIRS_NOAA20",),
    "viirs-noaa21": ("VIIRS_NOAA21",),
}
SOURCE_FAMILY_SENSORS: dict[str, tuple[str, ...]] = {
    "MODIS": ("MODIS_TERRA", "MODIS_AQUA"),
    "MODIS_TERRA": ("MODIS_TERRA",),
    "MODIS_AQUA": ("MODIS_AQUA",),
    "VIIRS_SNPP": ("VIIRS_SNPP",),
    "VIIRS_NOAA20": ("VIIRS_NOAA20",),
    "VIIRS_NOAA21": ("VIIRS_NOAA21",),
}

JORDAN_STUDY_BBOX = (34.0, 29.0, 40.0, 34.0)
JORDAN_API_BBOX = (34.8, 29.0, 39.4, 33.5)
LEVANT_STUDY_BBOX = (34.0, 29.0, 43.0, 38.0)

_REGION_PATH = Path(__file__).parent / "intelligence" / "regions.geojson"
_REGION_DATA = json.loads(_REGION_PATH.read_text(encoding="utf-8"))
JORDAN_REGIONS = {
    f["properties"]["region_id"]: shape(f["geometry"]) for f in _REGION_DATA["features"]
}
JORDAN_COUNTRY_POLYGON = unary_union(list(JORDAN_REGIONS.values()))
JORDAN_COUNTRY_GEOJSON = json.loads(json.dumps(JORDAN_COUNTRY_POLYGON.__geo_interface__))

NAMED_AREAS: dict[str, dict[str, Any]] = {
    "jordan_country": {
        "label": "Jordan country boundary (Natural Earth 1:110m union)",
        "bbox": None,
        "polygon": JORDAN_COUNTRY_GEOJSON,
    },
    "jordan_study_area": {
        "label": "Jordan study envelope [34, 29, 40, 34]",
        "bbox": list(JORDAN_STUDY_BBOX),
        "polygon": None,
    },
    "jordan_api_envelope": {
        "label": "Jordan API profile envelope [34.8, 29.0, 39.4, 33.5]",
        "bbox": list(JORDAN_API_BBOX),
        "polygon": None,
    },
    **{
        region_id: {
            "label": f["properties"]["label"],
            "bbox": None,
            "polygon": f["geometry"],
        }
        for f in _REGION_DATA["features"]
        for region_id in [f["properties"]["region_id"]]
    },
    "levant": {
        "label": "Levant study envelope [34, 29, 43, 38]",
        "bbox": list(LEVANT_STUDY_BBOX),
        "polygon": None,
    },
}


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    days = calendar.monthrange(year, month)[1]
    return start, start + timedelta(days=days)


def _bbox_geom(bbox: tuple[float, float, float, float] | list[float]):
    west, south, east, north = [float(v) for v in bbox]
    if west < east:
        return box(west, south, east, north)
    return box(west, south, 180.0, north).union(box(-180.0, south, east, north))


def _selection_geometry(
    bbox: tuple[float, float, float, float] | list[float] | None,
    polygon: dict[str, Any] | None,
):
    geom = None
    if bbox is not None:
        geom = _bbox_geom(bbox)
    if polygon is not None:
        poly = shape(polygon)
        geom = poly if geom is None else geom.intersection(poly)
    return geom


def classify_area(
    bbox: tuple[float, float, float, float] | list[float] | None,
    polygon: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify how a spatial selection relates to country and bounding-box archives."""
    norm_bbox = tuple(float(x) for x in bbox) if bbox is not None else None
    geom = _selection_geometry(norm_bbox, polygon)
    if geom is None or geom.is_empty:
        return {
            "area_kind": "empty",
            "covered_by_jordan_country": False,
            "is_jordan_study_envelope": False,
            "is_levant_envelope": False,
            "geometry": None,
        }
    # Small tolerance accounts for serialized coordinate rounding along shared vertices.
    covered_by_jordan = JORDAN_COUNTRY_POLYGON.buffer(1e-5).covers(geom)
    is_jordan_envelope = polygon is None and norm_bbox in {
        JORDAN_STUDY_BBOX,
        JORDAN_API_BBOX,
    }
    is_levant_envelope = polygon is None and norm_bbox == LEVANT_STUDY_BBOX
    return {
        "area_kind": (
            "jordan_polygon"
            if covered_by_jordan
            else "jordan_envelope"
            if is_jordan_envelope
            else "levant_envelope"
            if is_levant_envelope
            else "custom"
        ),
        "covered_by_jordan_country": bool(covered_by_jordan),
        "is_jordan_study_envelope": bool(is_jordan_envelope),
        "is_levant_envelope": bool(is_levant_envelope),
        "geometry": geom,
        "bbox": norm_bbox,
    }


def _source_is_clean(source: dict[str, Any]) -> bool:
    meta = source.get("source_metadata") or {}
    quality = source.get("quality_report") or meta.get("quality") or {}
    if quality.get("status") != "imported":
        return False
    if quality.get("invalid_rows") != 0:
        return False
    if not source.get("sha256") or quality.get("source_sha256") != source["sha256"]:
        return False
    return isinstance(quality.get("filters"), dict)


def _filters_cover_month_and_area(
    filters: dict[str, Any] | None,
    month_start: date,
    month_end: date,
    target_geom,
) -> bool:
    if not filters:
        return True
    start_str = filters.get("start")
    end_str = filters.get("end")
    if start_str:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).astimezone(UTC)
        if start_dt > datetime.combine(month_start, datetime.min.time(), tzinfo=UTC):
            return False
    if end_str:
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00")).astimezone(UTC)
        if end_dt < datetime.combine(month_end, datetime.min.time(), tzinfo=UTC):
            return False
    filter_bbox = filters.get("bbox")
    filter_poly = filters.get("polygon")
    if filter_bbox or filter_poly:
        filter_geom = _selection_geometry(filter_bbox, filter_poly)
        if filter_geom is None or not filter_geom.buffer(1e-5).covers(target_geom):
            return False
    return True


def extract_source_evidence(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Index validated annual country files and API day windows from source metadata."""
    country_files: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    api_windows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # Each successful import can contribute a different slice of the same file.
    imports = [
        {**source, "quality_report": report}
        for source in sources
        for report in source.get("quality_reports", [source.get("quality_report")])
    ]
    for source in sorted(
        imports,
        key=lambda s: (str(s.get("id", "")), json.dumps(s.get("quality_report"), sort_keys=True)),
    ):
        if not _source_is_clean(source):
            continue
        url = str(source.get("source_url") or "")
        meta = source.get("source_metadata") or {}
        quality = source.get("quality_report") or meta.get("quality") or {}
        filters = quality.get("filters") or source.get("filters")
        processing_level = str(source.get("processing_level") or "").lower()
        match = COUNTRY_URL_RE.match(url)
        if match and processing_level == "standard":
            product = match.group("product")
            year = int(match.group("year"))
            country = match.group("country")
            declared_sensors = SOURCE_FAMILY_SENSORS.get(str(source.get("sensor_code")), ())
            for sensor in PRODUCT_SENSORS.get(product, ()):
                if sensor not in declared_sensors:
                    continue
                country_files[sensor, year, country].append(
                    {
                        "id": str(source.get("id", "")),
                        "sha256": source.get("sha256", ""),
                        "original_filename": source.get("original_filename", ""),
                        "source_url": url,
                        "processing_level": processing_level,
                        "product_version": source.get("product_version", "native"),
                        "filters": filters,
                    }
                )
            continue
        report_req = (quality.get("request_metadata") or {}).get("request")
        request = report_req if isinstance(report_req, dict) else meta.get("request")
        if isinstance(request, dict) and request.get("start_date") and request.get("day_range"):
            try:
                win_start = date.fromisoformat(str(request["start_date"]))
                days = int(request["day_range"])
                req_bbox = tuple(float(x) for x in request["bbox"])
            except (KeyError, TypeError, ValueError):
                continue
            if days <= 0:
                continue
            win_end = win_start + timedelta(days=days)
            # Filters restrict a response; they cannot establish different request dates.
            declared_sensor = str(source.get("sensor_code") or "")
            req_source = str(request.get("source") or "")
            sensors = SOURCE_FAMILY_SENSORS.get(declared_sensor, ())
            if not sensors and req_source.startswith("MODIS"):
                sensors = ("MODIS_TERRA", "MODIS_AQUA")
            elif not sensors and req_source.startswith("VIIRS_SNPP"):
                sensors = ("VIIRS_SNPP",)
            for sensor in sensors:
                api_windows[sensor].append(
                    {
                        "id": str(source.get("id", "")),
                        "sha256": source.get("sha256", ""),
                        "original_filename": source.get("original_filename", ""),
                        "source_url": url,
                        "processing_level": processing_level,
                        "product_version": source.get("product_version", "native"),
                        "start_date": win_start,
                        "end_date": win_end,
                        "bbox": req_bbox,
                        "filters": filters,
                    }
                )
    return {"country_files": country_files, "api_windows": api_windows}


def audit_selection_completeness(
    *,
    start_year: int,
    end_year: int,
    sensors: list[str],
    bbox: tuple[float, float, float, float] | list[float] | None,
    polygon: dict[str, Any] | None,
    sources: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Audit archive completeness for every (sensor, YYYY-MM) in the requested selection."""
    area_info = classify_area(bbox, polygon)
    target_geom = area_info["geometry"]
    evidence = extract_source_evidence(sources)
    country_files = evidence["country_files"]
    api_windows = evidence["api_windows"]

    results: dict[tuple[str, str], dict[str, Any]] = {}
    for sensor in sensors:
        avail = SENSOR_AVAILABILITY.get(sensor, {})
        first_full = avail.get("first_full_month")
        partial_start = avail.get("partial_start_month")
        for year in range(start_year, end_year + 1):
            for month_num in range(1, 13):
                label = f"{year:04d}-{month_num:02d}"
                month_start, month_end = _month_bounds(year, month_num)

                # 1. Check sensor operational start / transition status.
                if partial_start and label == partial_start:
                    results[sensor, label] = {
                        "sensor_code": sensor,
                        "month": label,
                        "completeness": "unknown",
                        "archive_completeness": "partial",
                        "observation_coverage": "unknown",
                        "missing_data_status": "sensor_transition_partial_month",
                        "spatial_scope": None,
                        "processing_levels": [],
                        "reference": None,
                        "reason": (
                            f"{sensor} archive availability began {avail['operational_start']}; "
                            f"{label} is a partial sensor-start month."
                        ),
                    }
                    continue
                if first_full and label < first_full:
                    results[sensor, label] = {
                        "sensor_code": sensor,
                        "month": label,
                        "completeness": "unknown",
                        "archive_completeness": "unknown",
                        "observation_coverage": "unknown",
                        "missing_data_status": "pre_operational_sensor",
                        "spatial_scope": None,
                        "processing_levels": [],
                        "reference": None,
                        "reason": (
                            f"{label} precedes {sensor} operational availability "
                            f"({avail['operational_start']})."
                        ),
                    }
                    continue

                if target_geom is None:
                    results[sensor, label] = {
                        "sensor_code": sensor,
                        "month": label,
                        "completeness": "unknown",
                        "archive_completeness": "unknown",
                        "observation_coverage": "unknown",
                        "missing_data_status": "unattested_or_missing_source",
                        "spatial_scope": None,
                        "processing_levels": [],
                        "reference": None,
                        "reason": "No valid spatial selection.",
                    }
                    continue

                # 2. Check official NASA annual country summary CSV evidence.
                if area_info["covered_by_jordan_country"]:
                    candidates = [
                        item
                        for item in country_files.get((sensor, year, "Jordan"), [])
                        if _filters_cover_month_and_area(
                            item["filters"], month_start, month_end, target_geom
                        )
                    ]
                    if candidates:
                        chosen = candidates[0]
                        scope_tag = (
                            "jordan_polygon"
                            if area_info["covered_by_jordan_country"]
                            else "jordan_country"
                        )
                        ref = (
                            f"archive-audit:{chosen['original_filename'] or chosen['id']}"
                            f"#sha256:{chosen['sha256'][:12]}:{label}"
                        )
                        results[sensor, label] = {
                            "sensor_code": sensor,
                            "month": label,
                            "completeness": "complete",
                            "archive_completeness": "complete",
                            "observation_coverage": "unknown",
                            "missing_data_status": "complete_from_annual_source",
                            "spatial_scope": scope_tag,
                            "processing_levels": ["standard"],
                            "reference": ref,
                            "source_ids": [c["id"] for c in candidates if c["id"]],
                            "reason": (
                                "Validated NASA annual country summary file imported without "
                                "invalid or excluded in-scope records."
                            ),
                        }
                        continue
                # 3. Check bounded FIRMS Area API day windows covering this month.
                overlapping_windows = [
                    w
                    for w in api_windows.get(sensor, [])
                    if w["start_date"] < month_end and w["end_date"] > month_start
                ]
                if overlapping_windows:
                    # Check which windows spatially cover the target geometry or Jordan API bbox.
                    covering_windows = []
                    for w in overlapping_windows:
                        w_geom = _selection_geometry(w["bbox"], None)
                        if w_geom is not None and w_geom.buffer(1e-5).covers(target_geom):
                            covering_windows.append(w)

                    if covering_windows:
                        total_days = (month_end - month_start).days
                        day_levels: dict[date, set[str]] = defaultdict(set)
                        for d_offset in range(total_days):
                            day = month_start + timedelta(days=d_offset)
                            for w in covering_windows:
                                if w["start_date"] <= day < w[
                                    "end_date"
                                ] and _filters_cover_month_and_area(
                                    w["filters"], day, day + timedelta(days=1), target_geom
                                ):
                                    day_levels[day].add(w["processing_level"])
                        covered_days = len(day_levels)
                        all_levels = sorted({lvl for lvls in day_levels.values() for lvl in lvls})

                        if covered_days < total_days:
                            results[sensor, label] = {
                                "sensor_code": sensor,
                                "month": label,
                                "completeness": "unknown",
                                "archive_completeness": "partial",
                                "observation_coverage": "unknown",
                                "missing_data_status": "partial_month_archive",
                                "spatial_scope": "api_bbox",
                                "processing_levels": all_levels,
                                "reference": None,
                                "reason": (
                                    f"Only {covered_days} of {total_days} UTC days in {label} "
                                    "have imported API windows."
                                ),
                            }
                            continue

                        if len(all_levels) > 1 or any(
                            len(lvls) > 1 for lvls in day_levels.values()
                        ):
                            results[sensor, label] = {
                                "sensor_code": sensor,
                                "month": label,
                                "completeness": "unknown",
                                "archive_completeness": "unknown",
                                "observation_coverage": "unknown",
                                "missing_data_status": "mixed_processing_revisions",
                                "spatial_scope": "api_bbox",
                                "processing_levels": all_levels,
                                "reference": None,
                                "reason": (
                                    f"Month {label} mixes standard and NRT API revisions without "
                                    "an audited replacement policy."
                                ),
                            }
                            continue

                        # All days covered with a single processing level.
                        level = all_levels[0] if all_levels else "standard"
                        if level != "standard":
                            results[sensor, label] = {
                                "sensor_code": sensor,
                                "month": label,
                                "completeness": "unknown",
                                "archive_completeness": "nrt_complete",
                                "observation_coverage": "unknown",
                                "missing_data_status": "nrt_unreconciled",
                                "spatial_scope": (
                                    "jordan_polygon"
                                    if area_info["covered_by_jordan_country"]
                                    else "api_bbox"
                                ),
                                "processing_levels": ["nrt"],
                                "reference": None,
                                "reason": (
                                    f"All {total_days} UTC days of {label} were imported from "
                                    "near-real-time (NRT) API windows, which are not reconciled "
                                    "with standard-product baselines."
                                ),
                            }
                            continue

                        digest = hashlib.sha256(
                            "|".join(sorted(w["sha256"] for w in covering_windows)).encode()
                        ).hexdigest()[:12]
                        results[sensor, label] = {
                            "sensor_code": sensor,
                            "month": label,
                            "completeness": "complete",
                            "archive_completeness": "complete",
                            "observation_coverage": "unknown",
                            "missing_data_status": "complete_from_api_windows",
                            "spatial_scope": (
                                "jordan_polygon"
                                if area_info["covered_by_jordan_country"]
                                else "api_bbox"
                            ),
                            "processing_levels": ["standard"],
                            "reference": f"archive-audit:api-standard-{label}#sha256:{digest}",
                            "source_ids": sorted({w["id"] for w in covering_windows if w["id"]}),
                            "reason": (
                                f"All {total_days} UTC days of {label} covered by strictly "
                                "validated standard-product FIRMS API windows."
                            ),
                        }
                        continue

                # Country exports cannot establish completeness outside their boundary.
                scope_mismatch = (
                    not area_info["covered_by_jordan_country"]
                    and bool(country_files.get((sensor, year, "Jordan")))
                ) or bool(overlapping_windows)
                # 4. No source evidence covers this area, sensor, and month.
                results[sensor, label] = {
                    "sensor_code": sensor,
                    "month": label,
                    "completeness": "unknown",
                    "archive_completeness": "scope_mismatch" if scope_mismatch else "unknown",
                    "observation_coverage": "unknown",
                    "missing_data_status": (
                        "spatial_scope_mismatch"
                        if scope_mismatch
                        else "unattested_or_missing_source"
                    ),
                    "spatial_scope": None,
                    "processing_levels": [],
                    "reference": None,
                    "reason": "No validated full-month evidence covers this exact selection.",
                }
    return results


def build_archive_completeness_report(
    session,
    *,
    start_year: int = 2000,
    end_year: int = 2026,
    sensors: list[str] | None = None,
) -> dict[str, Any]:
    """Build a full, deterministic archive completeness report from database state."""
    from sqlalchemy import func, select

    from app.models import DataQualityReport, ImportCheckpoint, Observation, SourceFile

    selected_sensors = sorted(set(sensors or ["MODIS_TERRA", "MODIS_AQUA", "VIIRS_SNPP"]))
    quality_by_source = defaultdict(list)
    for row in session.scalars(
        select(DataQualityReport)
        .where(DataQualityReport.source_id.is_not(None))
        .order_by(
            DataQualityReport.source_id, DataQualityReport.created_at, DataQualityReport.job_id
        )
    ):
        quality_by_source[str(row.source_id)].append(row.report)
    sources = []
    for sf in session.scalars(select(SourceFile).order_by(SourceFile.id)):
        sources.append(
            {
                "id": str(sf.id),
                "sha256": sf.sha256,
                "original_filename": sf.original_filename,
                "source_url": sf.source_url,
                "sensor_code": sf.sensor_code,
                "product_version": sf.product_version,
                "processing_level": sf.processing_level,
                "retrieved_at": sf.retrieved_at.astimezone(UTC).isoformat(),
                "row_count": sf.row_count,
                "source_metadata": sf.source_metadata,
                "quality_reports": quality_by_source.get(str(sf.id), []),
            }
        )

    checkpoints = [
        {
            "source": cp.parameters.get("source", cp.stream_key),
            "anchor_start_inclusive": cp.parameters.get("anchor_start"),
            "processed_end_exclusive": cp.next_date.isoformat(),
            "bbox": cp.parameters.get("bbox"),
        }
        for cp in session.scalars(select(ImportCheckpoint))
    ]
    checkpoints.sort(key=lambda c: str(c["source"]))

    # Summarize per-sensor observation extents and months with/without detections.
    sensor_summaries: dict[str, Any] = {}
    for sensor in selected_sensors:
        count, first_dt, last_dt = session.execute(
            select(
                func.count(Observation.id),
                func.min(Observation.acquired_at),
                func.max(Observation.acquired_at),
            ).where(Observation.sensor_code == sensor)
        ).one()
        month_col = func.to_char(func.timezone("UTC", Observation.acquired_at), "YYYY-MM")
        observed_months = {
            row[0]
            for row in session.execute(
                select(month_col, func.count(Observation.id))
                .where(
                    Observation.sensor_code == sensor,
                    Observation.acquired_at >= datetime(start_year, 1, 1, tzinfo=UTC),
                    Observation.acquired_at < datetime(end_year + 1, 1, 1, tzinfo=UTC),
                )
                .group_by(month_col)
            ).all()
        }
        all_months = [
            f"{y:04d}-{m:02d}"
            for y in range(start_year, min(end_year, 2025) + 1)
            for m in range(1, 13)
        ]
        # Audit for Jordan study area (2000-2026) and Jordan country polygon (2000-2026).
        study_audit = audit_selection_completeness(
            start_year=start_year,
            end_year=end_year,
            sensors=[sensor],
            bbox=JORDAN_STUDY_BBOX,
            polygon=None,
            sources=sources,
        )
        country_audit = audit_selection_completeness(
            start_year=start_year,
            end_year=end_year,
            sensors=[sensor],
            bbox=None,
            polygon=JORDAN_COUNTRY_GEOJSON,
            sources=sources,
        )
        complete_study_months = sorted(
            m for (_s, m), info in study_audit.items() if info["completeness"] == "complete"
        )
        zero_confirmed_study_months = sorted(
            m for m in complete_study_months if m not in observed_months
        )
        unknown_without_detections = sorted(
            m
            for m in all_months
            if m not in observed_months and study_audit[sensor, m]["completeness"] != "complete"
        )
        sensor_summaries[sensor] = {
            "observations": int(count or 0),
            "first_detection_utc": first_dt.astimezone(UTC).isoformat() if first_dt else None,
            "last_detection_utc": last_dt.astimezone(UTC).isoformat() if last_dt else None,
            "operational_start": SENSOR_AVAILABILITY.get(sensor, {}).get("operational_start"),
            "first_full_month": SENSOR_AVAILABILITY.get(sensor, {}).get("first_full_month"),
            "partial_start_month": SENSOR_AVAILABILITY.get(sensor, {}).get("partial_start_month"),
            "observation_coverage": "unknown",
            "archive_complete_months_jordan_study": len(complete_study_months),
            "archive_complete_months_jordan_polygon": sum(
                1 for info in country_audit.values() if info["completeness"] == "complete"
            ),
            "zero_supported_months_jordan_study": zero_confirmed_study_months,
            "months_without_archived_detections_unknown": unknown_without_detections,
        }

    area_audits: dict[str, Any] = {}
    for area_id, spec in NAMED_AREAS.items():
        audit_map = audit_selection_completeness(
            start_year=start_year,
            end_year=end_year,
            sensors=selected_sensors,
            bbox=spec["bbox"],
            polygon=spec["polygon"],
            sources=sources,
        )
        by_sensor: dict[str, Any] = {}
        for sensor in selected_sensors:
            sensor_rows = [info for (s, _m), info in sorted(audit_map.items()) if s == sensor]
            complete_list = [r["month"] for r in sensor_rows if r["completeness"] == "complete"]
            partial_list = [
                r["month"] for r in sensor_rows if r["archive_completeness"] == "partial"
            ]
            nrt_list = [
                r["month"] for r in sensor_rows if r["missing_data_status"] == "nrt_unreconciled"
            ]
            scope_mismatch_list = [
                r["month"]
                for r in sensor_rows
                if r["missing_data_status"] == "spatial_scope_mismatch"
            ]
            pre_op_list = [
                r["month"]
                for r in sensor_rows
                if r["missing_data_status"] == "pre_operational_sensor"
            ]
            by_sensor[sensor] = {
                "complete_count": len(complete_list),
                "complete_range": (
                    f"{complete_list[0]}..{complete_list[-1]}" if complete_list else None
                ),
                "complete_months": complete_list,
                "partial_months": partial_list,
                "nrt_unreconciled_months": nrt_list,
                "spatial_scope_mismatch_months": scope_mismatch_list,
                "pre_operational_months_count": len(pre_op_list),
                "observation_coverage": "unknown",
            }
        area_audits[area_id] = {
            "label": spec["label"],
            "bbox": spec["bbox"],
            "has_polygon": spec["polygon"] is not None,
            "sensors": by_sensor,
        }

    canonical_payload = {
        "audit_version": AUDIT_VERSION,
        "start_year": start_year,
        "end_year": end_year,
        "sensors": selected_sensors,
        "source_sha256s": sorted({s["sha256"] for s in sources}),
        "api_checkpoints": checkpoints,
        "areas": area_audits,
    }
    audit_id = hashlib.sha256(
        json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "audit_id": audit_id,
        "audit_version": AUDIT_VERSION,
        "observation_coverage": "unknown",
        "observation_coverage_distinct_from_archive_completeness": True,
        "scope": (
            "Local normalized archive completeness audit by area, sensor, and UTC month. "
            "Archive completeness establishes that all FIRMS records from validated source "
            "files covering that area and full calendar month were imported; it does not "
            "establish satellite observation coverage (swath/cloud/smoke) or physical fire "
            "absence. Unknown and partial months remain unknown; zero is reported only where "
            "archive completeness is supported by source evidence."
        ),
        "start_year": start_year,
        "end_year": end_year,
        "source_file_count": len(sources),
        "sensors": sensor_summaries,
        "areas": area_audits,
        "api_checkpoints": checkpoints,
    }


def record_completeness_audit(
    factory,
    *,
    start_year: int = 2000,
    end_year: int = 2026,
    sensors: list[str] | None = None,
) -> dict[str, Any]:
    """Run the archive completeness audit and persist an AnalyticalResult in PostGIS."""
    from firescope_pipeline.jobs import run_job

    from app.models import AnalyticalResult

    parameters = {
        "audit_version": AUDIT_VERSION,
        "start_year": start_year,
        "end_year": end_year,
        "sensors": sorted(set(sensors or ["MODIS_TERRA", "MODIS_AQUA", "VIIRS_SNPP"])),
    }

    def operation(session, job_id):
        report = build_archive_completeness_report(
            session,
            start_year=start_year,
            end_year=end_year,
            sensors=parameters["sensors"],
        )
        session.add(
            AnalyticalResult(
                job_id=job_id,
                result_type="archive_completeness_audit",
                method_version=AUDIT_VERSION,
                parameters=parameters,
                result=report,
                uncertainty={
                    "archive_completeness_only": True,
                    "satellite_observation_coverage": "unknown",
                    "unknown_months_preserved": True,
                },
            )
        )
        return {
            "audit_id": report["audit_id"],
            "audit_version": AUDIT_VERSION,
            "source_file_count": report["source_file_count"],
            "report": report,
        }

    return run_job(factory, "analysis", AUDIT_VERSION, parameters, operation)
