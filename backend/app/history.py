"""Deterministic archive statistics; no coverage inference and no risk forecasts."""

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import Point, box, shape

from app.catalog import SENSOR_CODES
from app.completeness import (
    AUDIT_VERSION,
    SENSOR_AVAILABILITY,
    audit_selection_completeness,
)
from app.schemas import ObservationQuery

VERSION = "historical-activity-v2"
HISTORY_METRIC = "monthly_normalized_detection_count"
NOTES = {
    "count": "Exact-payload deduplicated thermal detections, not unique fires or burned area. "
    "Distinct overpasses and product revisions remain distinct. Sensors are never pooled.",
    "coverage": "Absent months are null, not zero. Positive counts do not establish completeness. "
    "Complete months are caller-attested or source-audited for this exact area and confidence "
    "selection; references are retained, not independently verified by PIRX. Archive "
    "completeness does not establish satellite exposure or fire absence.",
    "baseline": "Only complete months of the same sensor, area and calendar month are used "
    "(or the validated harmonized series when operational approval exists for the scope). "
    "Each target uses strictly earlier years within the requested baseline interval. "
    "Seasonal profiles describe the complete months of the fixed baseline interval.",
    "percentile": "Linear interpolation at (n-1)*p/100 over sorted reference counts. Strictly "
    "above the upper percentile is unusually high; strictly below the complementary "
    "lower percentile is unusually low. These are descriptive thresholds, not "
    "p-values, calibrated false-alarm probabilities, or fire-risk forecasts.",
    "robust_z": "(count - historical median)/(1.4826 * median absolute deviation). Null when "
    "MAD is zero or history is insufficient; percentile flags still apply.",
    "year_over_year": "Monthly changes require both complete equivalent months. Annual changes "
    "sum only the intersection of complete calendar months in adjacent years. "
    "Percent change is null for a zero previous count or no matched months.",
    "yearly": "Annual count is null unless all twelve months are complete. Observed count is "
    "a partial archive total, not an estimate of missing months.",
    "spatial": "Fixed WGS84 angular cells anchored at (-180,-90). Cell share is its count divided "
    "by all selected detections of that sensor. Herfindahl index is the sum of squared "
    "cell shares (0-1); top-10 share is the sum of the ten largest shares. "
    "These describe archived detections within each sensor and the fixed selection. "
    "Cells differ in physical area; this is not an area-normalized density, "
    "exposure-corrected concentration, significance test, or risk map.",
    "trend": "Monthly archived counts and prior-year medians; null months break lines. "
    "No extrapolation, machine learning, causal trend attribution or forecasting.",
    "harmonization": "Cross-sensor harmonization is applied only when a registered calibration "
    "model has status 'supported_for_scope', passes fingerprint and product-version checks, "
    "and covers the selected sensor pair. Candidate-only models are never applied.",
}


class CompleteMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sensor_code: str
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    reference: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_reference(self):
        if self.sensor_code not in SENSOR_CODES or not self.reference.strip():
            raise ValueError("Supply a known sensor and a nonblank coverage reference")
        return self


class HistoryQuery(ObservationQuery):
    start_year: int = Field(ge=1900, le=2099)
    end_year: int = Field(ge=1900, le=2099)
    baseline_start_year: int | None = Field(default=None, ge=1900, le=2099)
    baseline_end_year: int | None = Field(default=None, ge=1900, le=2099)
    percentile: float = Field(default=95, ge=50, lt=100, allow_inf_nan=False)
    min_baseline_years: int = Field(default=5, ge=3, le=30)
    grid_size_deg: float = Field(default=1)
    complete_months: list[CompleteMonth] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def historical_selection(self):
        if self.start is not None or self.end is not None or self.offset or self.limit != 2000:
            raise ValueError("Use whole start_year/end_year; no pagination or date filters")
        if not (self.bbox or self.polygon):
            raise ValueError("A fixed bbox or polygon is required for equivalent-area comparisons")
        if not self.start_year <= self.end_year or self.end_year - self.start_year > 49:
            raise ValueError("Select an ordered interval of at most 50 years")
        self.baseline_start_year = (
            self.baseline_start_year if self.baseline_start_year is not None else self.start_year
        )
        self.baseline_end_year = (
            self.baseline_end_year if self.baseline_end_year is not None else self.end_year
        )
        if not (
            self.start_year <= self.baseline_start_year <= self.baseline_end_year <= self.end_year
        ):
            raise ValueError("Baseline years must be ordered and inside the selected interval")
        if self.grid_size_deg not in (0.25, 0.5, 1, 2, 5):
            raise ValueError("grid_size_deg must be 0.25, 0.5, 1, 2 or 5")
        if set(self.sensors) - set(SENSOR_CODES):
            raise ValueError("Unknown sensor code")
        self.sensors = sorted(set(self.sensors or SENSOR_CODES))
        keys = [(c.sensor_code, c.month) for c in self.complete_months]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate complete-month declarations")
        for declaration in self.complete_months:
            if (
                declaration.sensor_code not in self.sensors
                or not self.start_year <= int(declaration.month[:4]) <= self.end_year
            ):
                raise ValueError("Coverage declarations must belong to the selected sensors/years")
        self.complete_months.sort(key=lambda c: (c.sensor_code, c.month))
        return self

    def observation_query(self):
        return ObservationQuery(
            bbox=self.bbox,
            polygon=self.polygon,
            sensors=self.sensors,
            confidence=self.confidence,
            start=datetime(self.start_year, 1, 1, tzinfo=UTC),
            end=datetime(self.end_year + 1, 1, 1, tzinfo=UTC),
        )


def percentile(values, p):
    ordered = sorted(values)
    index = (len(ordered) - 1) * p / 100
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def change(current, previous):
    return {
        "difference": current - previous,
        "percent_change": 100 * (current - previous) / previous if previous else None,
        "percent_change_reason": None if previous else "zero_previous_count",
    }


def _verify_calibration_model(
    entry: dict, query: HistoryQuery, sensor_versions: dict[str, set[str]]
) -> tuple[bool, str | None]:
    artifact = entry.get("artifact") or {}
    if not isinstance(artifact, dict) or "model_version" not in artifact:
        return False, "missing_model_artifact"
    core = {k: v for k, v in artifact.items() if k != "model_version"}
    expected_fp = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if artifact.get("model_version") != expected_fp or entry.get("model_version") not in (
        None,
        expected_fp,
    ):
        return False, "invalid_model_fingerprint"
    if entry.get("status") != "supported_for_scope":
        return False, "candidate_only_not_approved"
    if entry.get("method") not in ("regression", "quantile_mapping"):
        return False, "baseline_identity_not_calibration"
    validation = entry.get("validation") or {}
    if validation.get("status") != "evaluated":
        return False, "validation_not_evaluated"
    if validation.get("rejection_reasons"):
        return False, "validation_rejected"
    context = artifact.get("context") or {}
    # Grid-density/occupancy models must never consume raw monthly counts.
    if artifact.get("metric") != HISTORY_METRIC:
        return False, "unsupported_history_metric"
    if entry.get("metric", HISTORY_METRIC) != HISTORY_METRIC:
        return False, "model_metric_mismatch"
    if artifact.get("method") != entry.get("method") or artifact.get("bounded_occupancy"):
        return False, "model_contract_mismatch"
    scope = context.get("history_scope")
    if not isinstance(scope, dict):
        return False, "missing_history_scope"
    # Approval for a region's counts does not imply approval for arbitrary subsets.
    if not {"bbox", "polygon", "confidence", "start_year", "end_year"}.issubset(scope):
        return False, "incomplete_history_scope"

    def geometry(bbox, polygon):
        area = shape(polygon) if polygon else None
        if bbox:
            west, south, east, north = bbox
            bounds = (
                box(west, south, east, north)
                if west < east
                else box(west, south, 180, north).union(box(-180, south, east, north))
            )
            area = bounds if area is None else area.intersection(bounds)
        return area

    approved_area = geometry(scope["bbox"], scope["polygon"])
    selected_area = geometry(query.bbox, query.polygon)
    if approved_area is None or not approved_area.equals(selected_area):
        return False, "geographic_scope_mismatch"
    if scope["confidence"] != query.confidence:
        return False, "confidence_scope_mismatch"
    if not scope["start_year"] <= query.start_year <= query.end_year <= scope["end_year"]:
        return False, "temporal_scope_mismatch"
    if context.get("daynight") != "all" or context.get("grid_size_m") is not None:
        return False, "observation_stratum_or_grid_mismatch"
    source_sensor = context.get("source")
    reference_sensor = context.get("reference")
    if not source_sensor or not reference_sensor or source_sensor == reference_sensor:
        return False, "missing_sensor_pair"
    if not {source_sensor, reference_sensor}.issubset(query.sensors):
        return False, "sensor_pair_not_selected"
    native_versions = context.get("native_product_versions") or {}
    for s_code in (source_sensor, reference_sensor):
        allowed = {
            str(v) for v in native_versions.get(s_code, []) if v not in ("native", "test", "")
        }
        observed = {
            str(v) for v in sensor_versions.get(s_code, set()) if v not in ("native", "test", "")
        }
        if not allowed or not observed or not observed.issubset(allowed):
            return False, "product_version_transition_mismatch"
    return True, None


def _predict_calibrated_value(
    artifact: dict, count: float, calendar_month: int
) -> tuple[float, bool]:
    low, high = [float(v) for v in artifact["source_range"]]
    x = float(count)
    extrapolated = bool(x < low or x > high)
    method = artifact["method"]
    if method == "regression":
        angle = 2.0 * math.pi * (calendar_month - 1) / 12.0
        features = [
            1.0,
            math.log1p(x),
            math.sin(angle),
            math.cos(angle),
            math.sin(2.0 * angle),
            math.cos(2.0 * angle),
        ]
        coeffs = [float(c) for c in artifact["parameters"]["coefficients"]]
        z = sum(f * c for f, c in zip(features, coeffs, strict=True))
        pred = max(0.0, math.expm1(max(-50.0, min(50.0, z))))
    elif method == "quantile_mapping":
        quarter = str((calendar_month - 1) // 3 + 1)
        season = artifact["parameters"]["seasons"][quarter]
        params = artifact["parameters"]["global"] if "fallback" in season else season
        knots_x = [float(v) for v in params["x"]]
        knots_y = [float(v) for v in params["y"]]
        extrapolated = bool(x < knots_x[0] or x > knots_x[-1])
        if x <= knots_x[0]:
            pred = knots_y[0]
        elif x >= knots_x[-1]:
            pred = knots_y[-1]
        else:
            pred = knots_y[-1]
            for idx in range(len(knots_x) - 1):
                if knots_x[idx] <= x <= knots_x[idx + 1]:
                    span = knots_x[idx + 1] - knots_x[idx]
                    pred = (
                        knots_y[idx]
                        if span == 0
                        else knots_y[idx]
                        + (knots_y[idx + 1] - knots_y[idx]) * (x - knots_x[idx]) / span
                    )
                    break
    else:
        pred = x
    if artifact.get("bounded_occupancy"):
        pred = max(0.0, min(1.0, pred))
    return round(pred, 6), extrapolated


def analyze(
    query: HistoryQuery,
    records: list[dict],
    sources: list[dict],
    *,
    calibration_models: list[dict] | None = None,
    audit_sources: bool = True,
):
    """Apply the same area/time/sensor selection to every analytical period."""
    area = shape(query.polygon) if query.polygon else None
    bounds = None
    if query.bbox:
        west, south, east, north = query.bbox
        bounds = (
            box(west, south, east, north)
            if west < east
            else box(west, south, 180, north).union(box(-180, south, east, north))
        )
    selected = []
    for record in records:
        acquired = datetime.fromisoformat(record["acquired_at"])
        if acquired.utcoffset() is None:
            raise ValueError("Snapshot acquisition timestamps must be timezone-aware")
        acquired = acquired.astimezone(UTC)
        point = Point(record["longitude"], record["latitude"])
        if (
            record["sensor_code"] in query.sensors
            and query.start_year <= acquired.year <= query.end_year
            and (not query.confidence or record.get("confidence_class") == query.confidence)
            and (area is None or area.covers(point))
            and (bounds is None or bounds.covers(point))
        ):
            selected.append(
                {
                    **record,
                    "acquired_at": acquired.isoformat(),
                    "source_ids": sorted(set(record["source_ids"])),
                }
            )
    records = sorted(selected, key=lambda r: r["id"])
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Snapshot contains repeated observation IDs")
    if len({r["record_hash"] for r in records}) != len(records):
        raise ValueError("Snapshot contains repeated normalized payload hashes")
    all_sources = sorted({s["id"]: s for s in sources}.values(), key=lambda s: str(s["id"]))
    audited = audit_selection_completeness(
        start_year=query.start_year,
        end_year=query.end_year,
        sensors=query.sensors,
        bbox=query.bbox,
        polygon=query.polygon,
        sources=all_sources if audit_sources else [],
    )
    used_sources = {s for r in records for s in r["source_ids"]}
    audit_source_ids = {s for info in audited.values() for s in info.get("source_ids", [])}
    retained_ids = used_sources | audit_source_ids
    sources = sorted([s for s in all_sources if s["id"] in retained_ids], key=lambda s: s["id"])
    if not used_sources.issubset({s["id"] for s in sources}):
        raise ValueError("Snapshot is missing source metadata")

    # Track observed product versions and processing levels per sensor from retained sources.
    source_by_id = {s["id"]: s for s in sources}
    sensor_versions: dict[str, set[str]] = defaultdict(set)
    sensor_levels: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for sid in record["source_ids"]:
            src = source_by_id.get(sid)
            if src:
                if src.get("product_version"):
                    sensor_versions[record["sensor_code"]].add(str(src["product_version"]))
                if src.get("processing_level"):
                    sensor_levels[record["sensor_code"]].add(str(src["processing_level"]))
    for (sensor, _m), info in audited.items():
        for sid in info.get("source_ids", []):
            src = source_by_id.get(sid)
            if src:
                if src.get("product_version"):
                    sensor_versions[sensor].add(str(src["product_version"]))
                if src.get("processing_level"):
                    sensor_levels[sensor].add(str(src["processing_level"]))

    # Evaluate registered calibration models for scope and transition eligibility.
    evaluated_models = []
    applied_model = None
    for entry in sorted(calibration_models or [], key=lambda m: str(m.get("model_version", ""))):
        ok, rejection = _verify_calibration_model(entry, query, sensor_versions)
        ctx = (entry.get("artifact") or {}).get("context") or {}
        evaluated_models.append(
            {
                "model_version": entry.get("model_version"),
                "method": entry.get("method"),
                "status": entry.get("status"),
                "source_sensor": ctx.get("source"),
                "reference_sensor": ctx.get("reference"),
                "eligible": ok,
                "rejection_reason": rejection,
                "validation_rejection_reasons": (entry.get("validation") or {}).get(
                    "rejection_reasons", []
                ),
            }
        )
        if ok and applied_model is None:
            applied_model = entry

    inputs = {
        "algorithm_version": VERSION,
        "query": query.model_dump(mode="json"),
        "records": records,
        "sources": sources,
        **(
            {"calibration_model_version": applied_model["model_version"]}
            if applied_model is not None
            else {}
        ),
    }
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)
    analysis_id = hashlib.sha256(canonical.encode()).hexdigest()
    buckets, cells = defaultdict(list), defaultdict(list)
    size = query.grid_size_deg
    for record in records:
        month = datetime.fromisoformat(record["acquired_at"]).astimezone(UTC).strftime("%Y-%m")
        buckets[record["sensor_code"], month].append(record)
        # Clamp +180/+90 to the final cell, rather than creating an out-of-world cell.
        x = min(int(360 / size) - 1, math.floor((record["longitude"] + 180) / size))
        y = min(int(180 / size) - 1, math.floor((record["latitude"] + 90) / size))
        cells[record["sensor_code"], x, y].append(record)
    declared = {(c.sensor_code, c.month): c.reference for c in query.complete_months}

    cal_artifact = applied_model["artifact"] if applied_model else None
    cal_ctx = (cal_artifact or {}).get("context") or {}
    cal_source = cal_ctx.get("source")
    cal_reference = cal_ctx.get("reference")
    cal_version = applied_model["model_version"] if applied_model else None

    monthly, indexed = [], {}
    for sensor in query.sensors:
        for year in range(query.start_year, query.end_year + 1):
            for month in range(1, 13):
                label = f"{year:04d}-{month:02d}"
                rows = buckets[sensor, label]
                audit_info = audited[sensor, label]
                if (sensor, label) in declared:
                    complete = True
                    coverage_ref = declared[sensor, label]
                    completeness_origin = "caller_declaration"
                    archive_completeness = "complete"
                    raw_status = "complete_caller_declared"
                elif audit_info["completeness"] == "complete":
                    complete = True
                    coverage_ref = audit_info["reference"]
                    completeness_origin = "source_audit"
                    archive_completeness = audit_info["archive_completeness"]
                    raw_status = audit_info["missing_data_status"]
                else:
                    complete = False
                    coverage_ref = None
                    completeness_origin = "unattested"
                    archive_completeness = audit_info["archive_completeness"]
                    raw_status = audit_info["missing_data_status"]

                count = len(rows) if rows or complete else None
                harmonized_val = None
                harmonized_extrap = None
                comp_series = "native_sensor"
                comp_val = count
                model_ver = None
                if cal_artifact is not None and sensor in (cal_source, cal_reference):
                    comp_series = "validated_harmonized"
                    model_ver = cal_version
                    comp_val = None
                    if complete and count is not None:
                        if sensor == cal_source:
                            harmonized_val, harmonized_extrap = _predict_calibrated_value(
                                cal_artifact, count, month
                            )
                        else:
                            harmonized_val, harmonized_extrap = float(count), False
                        comp_val = harmonized_val

                row = {
                    "sensor_code": sensor,
                    "month": label,
                    "year": year,
                    "calendar_month": month,
                    "count": count,
                    "completeness": "complete" if complete else "unknown",
                    "archive_completeness": archive_completeness,
                    "completeness_origin": completeness_origin,
                    "observation_coverage": "unknown",
                    "coverage_reference": coverage_ref,
                    "source_ids": sorted({s for r in rows for s in r["source_ids"]}),
                    "completeness_source_ids": sorted(audit_info.get("source_ids", [])),
                    "comparison_series": comp_series,
                    "comparison_value": comp_val,
                    "comparison_units": (
                        f"{cal_reference}-equivalent detections per month"
                        if comp_series == "validated_harmonized"
                        else "detections per month"
                    ),
                    "harmonized_value": harmonized_val,
                    "harmonized_extrapolated": harmonized_extrap,
                    "calibration_model_version": model_ver,
                    "_raw_missing_status": raw_status,
                    "_audit_reason": audit_info["reason"],
                }
                indexed[sensor, year, month] = row
                monthly.append(row)

    seasonal = []
    for sensor in query.sensors:
        for month in range(1, 13):
            baseline = [
                indexed[sensor, year, month]
                for year in range(query.baseline_start_year, query.baseline_end_year + 1)
                if indexed[sensor, year, month]["completeness"] == "complete"
            ]
            counts = [r["comparison_value"] for r in baseline]
            seasonal.append(
                {
                    "sensor_code": sensor,
                    "calendar_month": month,
                    "comparison_series": (
                        "validated_harmonized"
                        if cal_artifact is not None and sensor in (cal_source, cal_reference)
                        else "native_sensor"
                    ),
                    "sample_years": [r["year"] for r in baseline],
                    "sample_size": len(counts),
                    "median": median(counts) if counts else None,
                    "lower_percentile": percentile(counts, 100 - query.percentile)
                    if len(counts) >= query.min_baseline_years
                    else None,
                    "upper_percentile": percentile(counts, query.percentile)
                    if len(counts) >= query.min_baseline_years
                    else None,
                }
            )

    baseline_interval_label = f"{query.baseline_start_year}–{query.baseline_end_year}"
    status_counts: dict[str, int] = defaultdict(int)
    for row in monthly:
        sensor, year, month = row["sensor_code"], row["year"], row["calendar_month"]
        raw_status = row.pop("_raw_missing_status")
        audit_reason = row.pop("_audit_reason")
        prior_end = min(year - 1, query.baseline_end_year)
        years = []
        values = []
        used_baseline_sensors = set()
        for y in range(query.baseline_start_year, prior_end + 1):
            cand = indexed[sensor, y, month]
            if cand["completeness"] == "complete":
                years.append(y)
                values.append(cand["comparison_value"])
                used_baseline_sensors.add(sensor)
            elif (
                cal_artifact is not None
                and sensor == cal_source
                and cal_reference in query.sensors
                and indexed[cal_reference, y, month]["completeness"] == "complete"
            ):
                years.append(y)
                values.append(indexed[cal_reference, y, month]["comparison_value"])
                used_baseline_sensors.add(cal_reference)

        enough = len(values) >= query.min_baseline_years
        center = median(values) if enough else None
        lower = percentile(values, 100 - query.percentile) if enough else None
        upper = percentile(values, query.percentile) if enough else None
        mad = median([abs(v - center) for v in values]) if enough else None
        eligible = row["completeness"] == "complete"
        status = "incomplete_period" if not eligible else "insufficient_history"
        target_val = row["comparison_value"]
        if eligible and enough and target_val is not None:
            status = (
                "unusually_high"
                if target_val > upper
                else "unusually_low"
                if target_val < lower
                else "within_range"
            )
        if not eligible:
            missing_status = raw_status
            missing_reason = audit_reason
        elif not enough:
            missing_status = "complete_insufficient_baseline"
            if prior_end < query.baseline_start_year:
                missing_reason = (
                    f"Archive month is complete ({raw_status}), but {year} has 0 prior years "
                    f"inside the {baseline_interval_label} baseline interval "
                    f"({query.min_baseline_years} required)."
                )
            else:
                missing_reason = (
                    f"Archive month is complete ({raw_status}), but only {len(values)} of "
                    f"{query.min_baseline_years} required prior complete reference years are "
                    f"available in {query.baseline_start_year}–{prior_end}."
                )
        else:
            missing_status = "complete_assessed"
            missing_reason = (
                f"Archive month is complete ({raw_status}) with {len(values)} prior complete "
                f"reference years ({years[0]}–{years[-1]}). Satellite observation coverage "
                "remains unknown."
            )
        status_counts[missing_status] += 1

        row_limitations = [
            (
                "Counts represent deduplicated satellite thermal-anomaly detections, "
                "not unique fires or burned area."
            ),
            (
                "Archive completeness is distinct from satellite observation coverage "
                "(swath, cloud, smoke), which is unknown."
            ),
        ]
        if row["comparison_series"] == "validated_harmonized":
            row_limitations.append(
                f"Comparison uses validated harmonized series ({cal_version[:12]}) mapped to "
                f"{cal_reference} reference scale, not physical fire truth."
            )
            if row["harmonized_extrapolated"]:
                row_limitations.append(
                    "Month activity falls outside the calibration training range; "
                    "harmonized estimate is extrapolated."
                )
        else:
            row_limitations.append(
                "No validated cross-sensor harmonization model is applied; "
                "comparison is restricted to native single-sensor history."
            )
        if not eligible or not enough:
            row_limitations.append(missing_reason)

        row.update(
            {
                "baseline_years": years,
                "baseline_size": len(values),
                "baseline_period": f"{years[0]}–{years[-1]}" if years else None,
                "baseline_window": (
                    f"{query.baseline_start_year}–{prior_end}"
                    if prior_end >= query.baseline_start_year
                    else None
                ),
                "min_baseline_years": query.min_baseline_years,
                "baseline_sensors": sorted(used_baseline_sensors) if years else [sensor],
                "historical_median": center,
                "lower_threshold": lower,
                "upper_threshold": upper,
                "anomaly_status": status,
                "missing_data_status": missing_status,
                "missing_data_reason": missing_reason,
                "limitations": row_limitations,
                "robust_z": (target_val - center) / (1.4826 * mad)
                if eligible and enough and mad and target_val is not None
                else None,
            }
        )
        previous = indexed.get((sensor, year - 1, month))
        if (
            cal_artifact is not None
            and sensor == cal_source
            and (not previous or previous["completeness"] != "complete")
            and cal_reference in query.sensors
        ):
            previous = indexed.get((cal_reference, year - 1, month))
        row["year_over_year"] = (
            {"status": "comparable", **change(target_val, previous["comparison_value"])}
            if eligible and previous and previous["completeness"] == "complete"
            else {
                "status": "incomplete_or_missing_pair",
                "difference": None,
                "percent_change": None,
                "percent_change_reason": "incomplete_or_missing_pair",
            }
        )
    yearly = []
    for sensor in query.sensors:
        for year in range(query.start_year, query.end_year + 1):
            rows = [indexed[sensor, year, m] for m in range(1, 13)]
            complete = [r["calendar_month"] for r in rows if r["completeness"] == "complete"]
            matched = [
                m
                for m in complete
                if (sensor, year - 1, m) in indexed
                and indexed[sensor, year - 1, m]["completeness"] == "complete"
            ]
            observed = [r["count"] for r in rows if r["count"] is not None]
            comparison = {
                "matched_months": matched,
                "current_count": None,
                "previous_count": None,
                "difference": None,
                "percent_change": None,
                "percent_change_reason": "no_matched_complete_months",
            }
            if matched:
                current = sum(indexed[sensor, year, m]["count"] for m in matched)
                previous = sum(indexed[sensor, year - 1, m]["count"] for m in matched)
                comparison.update(
                    current_count=current, previous_count=previous, **change(current, previous)
                )
            yearly.append(
                {
                    "sensor_code": sensor,
                    "year": year,
                    "observed_count": sum(observed) if observed else None,
                    "count": sum(observed) if len(complete) == 12 else None,
                    "complete_months": complete,
                    "year_over_year": comparison,
                }
            )
    spatial, concentration = [], []
    for sensor in query.sensors:
        selected = [(x, y, rs) for (s, x, y), rs in sorted(cells.items()) if s == sensor]
        total = sum(len(rs) for _, _, rs in selected)
        shares = sorted([len(rs) / total for _, _, rs in selected], reverse=True)
        concentration.append(
            {
                "sensor_code": sensor,
                "observed_count": total or None,
                "occupied_cells": len(shares),
                "herfindahl_index": sum(s * s for s in shares) if shares else None,
                "top_10_cells_share": sum(shares[:10]) if shares else None,
            }
        )
        for x, y, rows in selected:
            west, south = -180 + x * size, -90 + y * size
            spatial.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [west, south],
                                [west + size, south],
                                [west + size, south + size],
                                [west, south + size],
                                [west, south],
                            ]
                        ],
                    },
                    "properties": {
                        "sensor_code": sensor,
                        "grid_x": x,
                        "grid_y": y,
                        "count": len(rows),
                        "share": len(rows) / total,
                        "source_ids": sorted({s for r in rows for s in r["source_ids"]}),
                    },
                }
            )

    sensor_transitions = []
    for sensor in query.sensors:
        avail = SENSOR_AVAILABILITY.get(sensor, {})
        pre_op_count = sum(
            1
            for r in monthly
            if r["sensor_code"] == sensor and r["missing_data_status"] == "pre_operational_sensor"
        )
        partial_months = [
            r["month"]
            for r in monthly
            if r["sensor_code"] == sensor
            and r["missing_data_status"] == "sensor_transition_partial_month"
        ]
        if pre_op_count or partial_months:
            sensor_transitions.append(
                {
                    "sensor_code": sensor,
                    "transition_type": "sensor_operational_start",
                    "operational_start": avail.get("operational_start"),
                    "partial_start_month": avail.get("partial_start_month"),
                    "first_full_month": avail.get("first_full_month"),
                    "pre_operational_months_in_selection": pre_op_count,
                    "partial_transition_months_in_selection": partial_months,
                    "note": (
                        f"{sensor} operational archive began {avail.get('operational_start')}; "
                        + (
                            f"{avail.get('partial_start_month')} is a partial start month "
                            "and excluded from baselines; "
                            if avail.get("partial_start_month")
                            else ""
                        )
                        + f"first full archive month is {avail.get('first_full_month')}."
                    ),
                }
            )
        versions = sorted(sensor_versions.get(sensor, set()))
        levels = sorted(sensor_levels.get(sensor, set()))
        if len(versions) > 1 or len(levels) > 1:
            sensor_transitions.append(
                {
                    "sensor_code": sensor,
                    "transition_type": "processing_or_product_revision",
                    "product_versions": versions,
                    "processing_levels": levels,
                    "note": (
                        f"{sensor} spans product versions {versions} and "
                        f"processing levels {levels}; "
                        "NRT and mixed-revision months are excluded from standard baselines."
                    ),
                }
            )

    families = {SENSOR_AVAILABILITY.get(s, {}).get("family", s) for s in query.sensors}
    if len(families) > 1:
        sensor_transitions.append(
            {
                "sensor_code": ",".join(query.sensors),
                "transition_type": "cross_sensor_family",
                "applied_calibration_model": cal_version,
                "harmonized": applied_model is not None,
                "note": (
                    f"Validated calibration model {cal_version[:12]} harmonizes {cal_source} to "
                    f"{cal_reference} scale across sensor families."
                    if applied_model is not None
                    else "Multiple sensor families selected without an approved calibration model; "
                    "MODIS and VIIRS series remain strictly separate."
                ),
            }
        )

    harmonization_info = {
        "available": applied_model is not None,
        "applied": applied_model is not None,
        "status": (
            "supported_for_scope"
            if applied_model is not None
            else "candidate_only"
            if evaluated_models
            else "none_registered"
        ),
        "comparison_series": (
            "validated_harmonized" if applied_model is not None else "native_sensor"
        ),
        "model_version": cal_version,
        "method": applied_model.get("method") if applied_model else None,
        "source_sensor": cal_source,
        "reference_sensor": cal_reference,
        "candidate_models": evaluated_models,
        "reason": (
            f"Validated {applied_model['method']} model ({cal_version[:12]}) applied for "
            f"{cal_source} -> {cal_reference}."
            if applied_model is not None
            else (
                "Registered models are not eligible for this query's metric, validated scope, "
                "versions or approval status; native single-sensor series are used. "
                "See candidate_models for rejection reasons."
                if evaluated_models
                else "No validated calibration model is registered for this selection; "
                "native single-sensor series are used."
            )
        ),
    }

    global_limitations = [
        NOTES["count"],
        NOTES["coverage"],
        (
            "Archive completeness records source-file ingestion for the selected area and month; "
            "satellite observation coverage (swath, cloud, smoke) remains unknown."
        ),
        harmonization_info["reason"],
    ]
    if status_counts.get("spatial_scope_mismatch"):
        global_limitations.append(
            "Some source footprints do not cover the exact selected area. Country exports "
            "cannot certify a larger rectangle; select a covered polygon or import sources "
            "covering the entire selection."
        )
    if status_counts.get("nrt_unreconciled"):
        global_limitations.append(
            "Near-real-time (NRT) API months are retained for situational inspection "
            "but excluded from standard-product historical baselines."
        )

    return {
        "analysis_id": analysis_id,
        "algorithm_version": VERSION,
        "query": query.model_dump(mode="json"),
        "time_zone": "UTC",
        "baseline_period": baseline_interval_label,
        "min_baseline_years": query.min_baseline_years,
        "observation_coverage": "unknown",
        "completeness_summary": {
            "audit_version": AUDIT_VERSION,
            "observation_coverage": "unknown",
            "complete_months_count": sum(1 for r in monthly if r["completeness"] == "complete"),
            "unknown_months_count": sum(1 for r in monthly if r["completeness"] != "complete"),
            "assessed_months_count": sum(
                1
                for r in monthly
                if r["anomaly_status"] in {"within_range", "unusually_high", "unusually_low"}
            ),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "harmonization": harmonization_info,
        "sensor_transitions": sensor_transitions,
        "limitations": global_limitations,
        "metric_explanations": NOTES,
        "forecasting": False,
        "sources": sources,
        "monthly": monthly,
        "yearly": yearly,
        "seasonal_profiles": seasonal,
        "spatial": {"type": "FeatureCollection", "features": spatial},
        "concentration": concentration,
    }


def calendar_csv(result):
    output = io.StringIO(newline="")
    fields = [
        "sensor_code",
        "month",
        "count",
        "completeness",
        "archive_completeness",
        "observation_coverage",
        "missing_data_status",
        "missing_data_reason",
        "coverage_reference_json",
        "comparison_series",
        "comparison_value",
        "comparison_units",
        "harmonized_value",
        "calibration_model_version",
        "historical_median",
        "baseline_period",
        "min_baseline_years",
        "baseline_size",
        "baseline_years_json",
        "lower_threshold",
        "upper_threshold",
        "anomaly_status",
        "robust_z",
        "yoy_difference",
        "yoy_percent_change",
        "limitations_json",
        "analysis_id",
        "algorithm_version",
        "query_json",
        "source_metadata_json",
        "science_note",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    source_index = {s["id"]: s for s in result["sources"]}
    for row in result["monthly"]:
        export = {k: row[k] for k in fields if k in row}
        export.update(
            coverage_reference_json=json.dumps(row["coverage_reference"]),
            baseline_years_json=json.dumps(row["baseline_years"]),
            limitations_json=json.dumps(row.get("limitations", [])),
            yoy_difference=row["year_over_year"]["difference"],
            yoy_percent_change=row["year_over_year"]["percent_change"],
            analysis_id=result["analysis_id"],
            algorithm_version=VERSION,
            query_json=json.dumps(result["query"], sort_keys=True),
            source_metadata_json=json.dumps(
                [source_index[s] for s in row["source_ids"] if s in source_index], sort_keys=True
            ),
            science_note=NOTES["count"] + " " + NOTES["coverage"],
        )
        writer.writerow(export)
    return output.getvalue()
