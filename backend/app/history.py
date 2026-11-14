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
from app.schemas import ObservationQuery

VERSION = "historical-activity-v1"
NOTES = {
    "count": "Exact-payload deduplicated thermal detections, not unique fires or burned area. "
    "Distinct overpasses and product revisions remain distinct. Sensors are never pooled.",
    "coverage": "Absent months are null, not zero. Positive counts do not establish completeness. "
    "Complete months are caller-attested for this exact area and confidence selection; "
    "references are retained, not independently verified by PIRX. Archive "
    "completeness does not establish satellite exposure or fire absence.",
    "baseline": "Only complete months of the same sensor, area and calendar month are used. "
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


def analyze(query: HistoryQuery, records: list[dict], sources: list[dict]):
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
    used_sources = {s for r in records for s in r["source_ids"]}
    sources = sorted([s for s in sources if s["id"] in used_sources], key=lambda s: s["id"])
    if used_sources != {s["id"] for s in sources}:
        raise ValueError("Snapshot is missing source metadata")
    inputs = {
        "algorithm_version": VERSION,
        "query": query.model_dump(mode="json"),
        "records": records,
        "sources": sources,
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
    coverage = {(c.sensor_code, c.month): c.reference for c in query.complete_months}
    monthly, indexed = [], {}
    for sensor in query.sensors:
        for year in range(query.start_year, query.end_year + 1):
            for month in range(1, 13):
                label = f"{year:04d}-{month:02d}"
                rows = buckets[sensor, label]
                complete = (sensor, label) in coverage
                count = len(rows) if rows or complete else None
                row = {
                    "sensor_code": sensor,
                    "month": label,
                    "year": year,
                    "calendar_month": month,
                    "count": count,
                    "completeness": "complete" if complete else "unknown",
                    "coverage_reference": coverage.get((sensor, label)),
                    "source_ids": sorted({s for r in rows for s in r["source_ids"]}),
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
            counts = [r["count"] for r in baseline]
            seasonal.append(
                {
                    "sensor_code": sensor,
                    "calendar_month": month,
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
    for row in monthly:
        sensor, year, month = row["sensor_code"], row["year"], row["calendar_month"]
        years = [
            y
            for y in range(query.baseline_start_year, min(year - 1, query.baseline_end_year) + 1)
            if indexed[sensor, y, month]["completeness"] == "complete"
        ]
        counts = [indexed[sensor, y, month]["count"] for y in years]
        enough = len(counts) >= query.min_baseline_years
        center = median(counts) if enough else None
        lower = percentile(counts, 100 - query.percentile) if enough else None
        upper = percentile(counts, query.percentile) if enough else None
        mad = median([abs(v - center) for v in counts]) if enough else None
        eligible = row["completeness"] == "complete"
        status = "incomplete_period" if not eligible else "insufficient_history"
        if eligible and enough:
            status = (
                "unusually_high"
                if row["count"] > upper
                else "unusually_low"
                if row["count"] < lower
                else "within_range"
            )
        row.update(
            {
                "baseline_years": years,
                "baseline_size": len(counts),
                "historical_median": center,
                "lower_threshold": lower,
                "upper_threshold": upper,
                "anomaly_status": status,
                "robust_z": (row["count"] - center) / (1.4826 * mad)
                if eligible and enough and mad
                else None,
            }
        )
        previous = indexed.get((sensor, year - 1, month))
        row["year_over_year"] = (
            {"status": "comparable", **change(row["count"], previous["count"])}
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
    return {
        "analysis_id": analysis_id,
        "algorithm_version": VERSION,
        "query": query.model_dump(mode="json"),
        "time_zone": "UTC",
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
        "coverage_reference_json",
        "historical_median",
        "baseline_size",
        "baseline_years_json",
        "lower_threshold",
        "upper_threshold",
        "anomaly_status",
        "robust_z",
        "yoy_difference",
        "yoy_percent_change",
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
            yoy_difference=row["year_over_year"]["difference"],
            yoy_percent_change=row["year_over_year"]["percent_change"],
            analysis_id=result["analysis_id"],
            algorithm_version=VERSION,
            query_json=json.dumps(result["query"], sort_keys=True),
            source_metadata_json=json.dumps(
                [source_index[s] for s in row["source_ids"]], sort_keys=True
            ),
            science_note=NOTES["count"] + " " + NOTES["coverage"],
        )
        writer.writerow(export)
    return output.getvalue()
