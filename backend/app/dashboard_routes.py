"""Read-only dashboard comparisons of persisted aggregates with equivalent archive bins."""

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from firescope_pipeline.calibration.io import code_hash
from firescope_pipeline.calibration.models import fingerprint, predict_model
from firescope_pipeline.calibration.validation import (
    metric_intervals,
    metrics,
    seasonal_metrics,
    trend_metrics,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.catalog import SENSOR_CODES
from app.db import get_session
from app.models import (
    AggregateSource,
    HarmonizedAggregate,
    Observation,
    ObservationRecord,
    ProcessingJob,
    RawRecord,
    SourceFile,
)
from app.repository import observation_filters, spatial_filters
from app.schemas import ObservationQuery

router = APIRouter(prefix="/api/v1", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]
VALIDATION_ROOT = Path(__file__).resolve().parents[2] / "docs/reports/harmonization"


def validate(query):
    if set(query.sensors) - set(SENSOR_CODES):
        raise HTTPException(422, "Unknown sensor code")


def whole_days(start, end):
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    first = datetime.combine(start.date(), time(), UTC)
    if start != first:
        first += timedelta(days=1)
    last = datetime.combine(end.date(), time(), UTC)
    return first, last


@router.post("/analytics/comparison/{job_id}")
def compare_aggregate(job_id: UUID, query: ObservationQuery, session: SessionDep):
    validate(query)
    if not query.start or not query.end or not (query.bbox or query.polygon):
        raise HTTPException(422, "Comparison requires a fixed area and start/end timestamps")
    if query.confidence:
        raise HTTPException(
            422, "Stored aggregates cannot be split by confidence; select all classes"
        )
    job = session.get(ProcessingJob, job_id)
    if not job or job.kind != "aggregate" or job.status != "succeeded":
        raise HTTPException(404, "Successful aggregate job not found")
    if job.algorithm_version != "wgs84-grid-daily-v2":
        raise HTTPException(
            422, "Unsupported aggregate algorithm; recreate with the current pipeline"
        )
    try:
        job_start = datetime.fromisoformat(job.parameters["start"])
        job_end = datetime.fromisoformat(job.parameters["end"])
        size = float(job.parameters["grid_size_deg"])
        if job_start.utcoffset() is None or job_end.utcoffset() is None or not 0.01 <= size <= 5:
            raise ValueError("Unsupported aggregate metadata")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "Aggregate lacks supported grid/time metadata") from exc
    first, last = whole_days(max(query.start, job_start), min(query.end, job_end))
    conditions = [
        HarmonizedAggregate.job_id == job_id,
        HarmonizedAggregate.day >= first.date(),
        HarmonizedAggregate.day < last.date(),
        *spatial_filters(query, HarmonizedAggregate.cell),
    ]
    if query.sensors:
        conditions.append(HarmonizedAggregate.sensor_code.in_(query.sensors))
    matched = (
        select(
            HarmonizedAggregate.sensor_code,
            HarmonizedAggregate.day,
            HarmonizedAggregate.grid_x,
            HarmonizedAggregate.grid_y,
            HarmonizedAggregate.detection_count,
        )
        .where(*conditions)
        .cte("matched_bins")
    )
    stored = session.execute(
        select(
            matched.c.sensor_code,
            matched.c.day,
            func.sum(matched.c.detection_count).label("count"),
            func.count().label("cells"),
        )
        .group_by(matched.c.sensor_code, matched.c.day)
        .order_by(
            matched.c.sensor_code,
            matched.c.day,
        )
    ).all()
    # EXISTS preserves one normalized detection when several raw source copies are linked.
    lineage = (
        select(ObservationRecord.observation_id)
        .join(
            RawRecord,
            RawRecord.id == ObservationRecord.raw_record_id,
        )
        .join(AggregateSource, AggregateSource.source_id == RawRecord.source_id)
        .where(
            AggregateSource.job_id == job_id,
            ObservationRecord.observation_id == Observation.id,
        )
        .exists()
    )
    day = func.date(func.timezone("UTC", Observation.acquired_at))
    x = func.least(func.floor((Observation.longitude + 180) / size), round(360 / size) - 1)
    y = func.least(func.floor((Observation.latitude + 90) / size), round(180 / size) - 1)
    raw = session.execute(
        select(
            Observation.sensor_code,
            day.label("day"),
            func.count(Observation.id).label("count"),
        )
        .join(
            matched,
            and_(
                Observation.sensor_code == matched.c.sensor_code,
                day == matched.c.day,
                x == matched.c.grid_x,
                y == matched.c.grid_y,
            ),
        )
        .where(
            lineage,
            *observation_filters(query),
            Observation.acquired_at >= first,
            Observation.acquired_at < last,
        )
        .group_by(
            Observation.sensor_code,
            day,
        )
    ).all()
    raw_index = {(r.sensor_code, r.day): int(r._mapping["count"]) for r in raw}
    daily = [
        {
            "sensor_code": r.sensor_code,
            "day": r.day.isoformat(),
            "raw_count": raw_index.get((r.sensor_code, r.day), 0),
            "grid_count": int(r._mapping["count"]),
            "occupied_cells": int(r.cells),
        }
        for r in stored
    ]
    return {
        "job_id": str(job_id),
        "algorithm_version": job.algorithm_version,
        "parameters": job.parameters,
        "provenance": job.output_metadata,
        "query": query.model_dump(mode="json"),
        "daily": daily,
        "raw_count": sum(r["raw_count"] for r in daily) if daily else None,
        "grid_count": sum(r["grid_count"] for r in daily) if daily else None,
        "archive_counts_match": all(r["raw_count"] == r["grid_count"] for r in daily)
        if daily
        else None,
        "scope": "Only full UTC days and occupied grid cells wholly inside the selected area, "
        "shared with the stored job. Raw counts use its linked source files. "
        "Boundary cells and unrepresented bins are excluded. Archive changes may "
        "alter recomputed counts; equal counts do not prove snapshot identity.",
        "method": "Common grid/day aggregation, separated by sensor. No sensor-bias "
        "correction or operational calibration; counts are thermal detections.",
    }


def safe_text(value):
    value = str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


@router.post("/observations/export.csv", response_class=Response)
def observation_csv(query: ObservationQuery, session: SessionDep):
    validate(query)
    rows = session.execute(
        select(
            Observation.id,
            Observation.sensor_code,
            Observation.acquired_at,
            Observation.longitude,
            Observation.latitude,
            Observation.frp_mw,
            Observation.confidence_native,
            Observation.confidence_class,
            Observation.source_row,
            Observation.uncertainty,
            SourceFile.id.label("source_id"),
            SourceFile.sha256,
            SourceFile.original_filename,
            SourceFile.source_url,
            SourceFile.product_version,
            SourceFile.processing_level,
            SourceFile.retrieved_at,
        )
        .join(SourceFile, SourceFile.id == Observation.source_id)
        .where(
            *observation_filters(query),
        )
        .order_by(Observation.acquired_at, Observation.id)
        .limit(250001)
    ).all()
    if len(rows) > 250000:
        raise HTTPException(413, "CSV selection exceeds 250,000 detections; narrow the filters")
    output = io.StringIO(newline="")
    fields = [
        "id",
        "sensor_code",
        "acquired_at",
        "longitude",
        "latitude",
        "frp_mw",
        "confidence_native",
        "confidence_class",
        "source_row",
        "source_id",
        "sha256",
        "original_filename",
        "source_url",
        "product_version",
        "processing_level",
        "retrieved_at",
        "uncertainty",
        "query_json",
        "science_note",
    ]
    writer = csv.DictWriter(output, fields, lineterminator="\n")
    writer.writeheader()
    selection = json.dumps(query.model_dump(mode="json"), sort_keys=True)
    for row in rows:
        item = {}
        for key, value in row._mapping.items():
            if isinstance(value, datetime):
                value = value.astimezone(UTC).isoformat()
            elif isinstance(value, dict):
                value = json.dumps(value, sort_keys=True)
            item[key] = safe_text(value) if isinstance(value, (str, UUID)) else value
        item.update(
            query_json=selection,
            science_note="Thermal detections, not unique fires. "
            "Primary source metadata; all source copies are available in observation detail.",
        )
        writer.writerow(item)
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pirx-detections.csv"'},
    )


class HarmonizationSelection(BaseModel):
    """Read-only teaching prototype, separate from persisted scientific aggregates."""

    model_config = ConfigDict(extra="forbid")
    year: int = Field(default=2024, ge=2000, le=2099)
    month: int = Field(default=7, ge=1, le=12)
    sensor_family: Literal["both", "MODIS", "VIIRS"] = "both"
    modis_confidence_min: int = Field(default=50, ge=0, le=100)
    viirs_confidence: Literal["nominal_high", "high", "all"] = "nominal_high"
    bbox: tuple[float, float, float, float] = (34, 29, 40, 34)

    @field_validator("bbox")
    @classmethod
    def validate_area(cls, value):
        return ObservationQuery(bbox=value).bbox


def prototype_grid(latitude: float, longitude: float):
    # Match JavaScript Math.round, including negative half ties, as specified by the brief.
    lat = math.floor(latitude * 100 + 0.5) / 100
    lon = math.floor(longitude * 100 + 0.5) / 100
    return lat, lon, f"{lat:.2f}_{lon:.2f}"


def prototype_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def prototype_accepts(record, query: HarmonizationSelection):
    native = str(record["confidence_native"]).strip().lower()
    if record["sensor_code"].startswith("MODIS"):
        number = prototype_number(native)
        return number is not None and query.modis_confidence_min <= number <= 100
    categories = {
        "nominal_high": {"n", "nominal", "h", "high"},
        "high": {"h", "high"},
        "all": {"l", "low", "n", "nominal", "h", "high"},
    }
    return native in categories[query.viirs_confidence]


def prototype_cells(records):
    cells = defaultdict(list)
    for record in records:
        lat, lon, grid_id = prototype_grid(record["latitude"], record["longitude"])
        cells[(record["day"], grid_id, lat, lon)].append(record)
    return cells


def prototype_frp(records):
    known = [r["frp_mw"] for r in records if r["frp_mw"] is not None]
    return sum(known) if known else None


def analyze_harmonization(query: HarmonizationSelection, records: list[dict], sources: list[dict]):
    """Deterministic prototype statistics over canonical observations, with no writes."""
    records = sorted(records, key=lambda r: r["id"])
    sources = sorted(sources, key=lambda source: source["id"])
    for record in records:
        if not record["sensor_code"].startswith(("MODIS", "VIIRS")):
            raise ValueError("Prototype input must contain MODIS or VIIRS observations")
    accepted_all = [r for r in records if prototype_accepts(r, query)]
    scoped = [
        r
        for r in records
        if query.sensor_family == "both" or r["sensor_code"].startswith(query.sensor_family)
    ]
    accepted = [
        r
        for r in accepted_all
        if query.sensor_family == "both" or r["sensor_code"].startswith(query.sensor_family)
    ]
    selected = [r for r in scoped if r["year"] == query.year and r["month"] == query.month]
    selected_accepted = [
        r for r in accepted if r["year"] == query.year and r["month"] == query.month
    ]
    grouped = prototype_cells(selected_accepted)
    cells = []
    for (day, grid_id, lat, lon), members in sorted(grouped.items()):
        frp = [r["frp_mw"] for r in members if r["frp_mw"] is not None]
        temperatures = [r["brightness_k"] for r in members if r["brightness_k"] is not None]
        cells.append(
            {
                "key": f"{day}_{grid_id}",
                "acq_date": day,
                "grid_id": grid_id,
                "grid_lat": lat,
                "grid_lon": lon,
                "unified_fire_count": 1,
                "raw_detections_count": len(members),
                "total_frp_mw": sum(frp) if frp else None,
                "mean_frp_mw": sum(frp) / len(frp) if frp else None,
                "frp_known_count": len(frp),
                "max_temp_k": max(temperatures) if temperatures else None,
                "temperature_known_count": len(temperatures),
                "sensors_involved": sorted({r["sensor_code"] for r in members}),
                "day_detections": sum(r["daynight"] == "D" for r in members),
                "night_detections": sum(r["daynight"] == "N" for r in members),
                "members": [
                    {
                        k: r[k]
                        for k in (
                            "id",
                            "sensor_code",
                            "latitude",
                            "longitude",
                            "confidence_native",
                            "frp_mw",
                            "brightness_k",
                            "brightness_field",
                            "daynight",
                            "source_id",
                            "source_row",
                        )
                    }
                    for r in members[:20]
                ],
                "members_truncated": len(members) > 20,
            }
        )
    years = sorted({r["year"] for r in records} | {query.year})
    annual = defaultdict(list)
    filtered_annual = defaultdict(list)
    monthly = defaultdict(list)
    filtered_monthly = defaultdict(list)
    for record in scoped:
        if record["month"] == query.month:
            annual[record["year"]].append(record)
        if record["year"] == query.year:
            monthly[record["month"]].append(record)
    for record in accepted:
        if record["month"] == query.month:
            filtered_annual[record["year"]].append(record)
        if record["year"] == query.year:
            filtered_monthly[record["month"]].append(record)

    def period(label, raw, retained):
        modis = [r for r in raw if r["sensor_code"].startswith("MODIS")]
        viirs = [r for r in raw if r["sensor_code"].startswith("VIIRS")]
        return {
            "label": str(label),
            "raw_modis": len(modis) if modis else None,
            "raw_viirs": len(viirs) if viirs else None,
            "accepted_count": len(retained) if raw else None,
            "unified_cell_days": len(prototype_cells(retained)) if raw else None,
            "frp_before_modis": prototype_frp(modis),
            "frp_before_viirs": prototype_frp(viirs),
            "frp_after_total": prototype_frp(retained),
            "frp_after_known_count": sum(r["frp_mw"] is not None for r in retained),
            "coverage": "unknown",
        }

    overlap_records = [
        r for r in accepted_all if 2012 <= r["year"] <= 2024 and r["month"] == query.month
    ]
    modis_overlap = [r for r in overlap_records if r["sensor_code"].startswith("MODIS")]
    viirs_overlap = [r for r in overlap_records if r["sensor_code"].startswith("VIIRS")]
    modis_keys, viirs_keys = (
        set(prototype_cells(modis_overlap)),
        set(prototype_cells(viirs_overlap)),
    )
    union, shared = modis_keys | viirs_keys, modis_keys & viirs_keys
    fingerprint = {
        "version": "rounded-001deg-cell-day-prototype-v1",
        "query": query.model_dump(mode="json"),
        "records": records,
        "sources": sources,
    }
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(fingerprint):
        digest.update(chunk.encode())
    analysis_id = digest.hexdigest()
    return {
        "analysis_id": analysis_id,
        "algorithm_version": fingerprint["version"],
        "query": query.model_dump(mode="json"),
        "available_years": years,
        "summary": {
            "input_detections": len(selected),
            "accepted_detections": len(selected_accepted),
            "rejected_detections": len(selected) - len(selected_accepted),
            "retention_percent": 100 * len(selected_accepted) / len(selected) if selected else None,
            "unified_cell_days": len(grouped),
            "total_frp_mw": prototype_frp(selected_accepted),
            "frp_known_count": sum(r["frp_mw"] is not None for r in selected_accepted),
        },
        "annual": [
            period(year, annual[year], filtered_annual[year])
            for year in range(min(years), max(years) + 1)
        ],
        "monthly": [
            period(f"{query.year}-{month:02d}", monthly[month], filtered_monthly[month])
            for month in range(1, 13)
        ],
        "overlap": {
            "start_year": 2012,
            "end_year": 2024,
            "calendar_month": query.month,
            "scope": "Both sensor families, same area, calendar month and confidence rules.",
            "modis_detections": len(modis_overlap),
            "viirs_detections": len(viirs_overlap),
            "modis_cell_days": len(modis_keys),
            "viirs_cell_days": len(viirs_keys),
            "shared_cell_days": len(shared),
            "modis_only_cell_days": len(modis_keys - viirs_keys),
            "viirs_only_cell_days": len(viirs_keys - modis_keys),
            "union_cell_days": len(union),
            "jaccard": len(shared) / len(union) if modis_keys and viirs_keys else None,
            "both_families_present": bool(modis_overlap and viirs_overlap),
        },
        "cells": cells[:200],
        "cells_total": len(cells),
        "cells_truncated": len(cells) > 200,
        "sources": sources,
        "coverage": "unknown",
        "operational_calibration": False,
    }


@router.post("/analytics/harmonization")
def harmonization_engine(query: HarmonizationSelection, session: SessionDep):
    selection = ObservationQuery(bbox=query.bbox)
    rows = session.execute(
        select(
            Observation.id,
            Observation.sensor_code,
            Observation.acquired_at,
            Observation.latitude,
            Observation.longitude,
            Observation.frp_mw,
            Observation.confidence_native,
            Observation.daynight,
            Observation.source_id,
            Observation.source_row,
            case(
                (
                    Observation.sensor_code.startswith("MODIS"),
                    RawRecord.raw_properties["brightness"].as_string(),
                ),
                else_=RawRecord.raw_properties["bright_ti4"].as_string(),
            ).label("brightness_native"),
        )
        .join(
            RawRecord,
            and_(
                RawRecord.source_id == Observation.source_id,
                RawRecord.source_row == Observation.source_row,
            ),
        )
        .where(*observation_filters(selection))
        .order_by(Observation.id)
        .limit(250001)
    ).all()
    if len(rows) > 250000:
        raise HTTPException(
            413, "Prototype selection exceeds 250,000 observations; narrow the area"
        )
    records = []
    for row in rows:
        acquired = row.acquired_at.astimezone(UTC)
        brightness_field = "brightness" if row.sensor_code.startswith("MODIS") else "bright_ti4"
        records.append(
            {
                "id": row.id,
                "sensor_code": row.sensor_code,
                "day": acquired.date().isoformat(),
                "year": acquired.year,
                "month": acquired.month,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "frp_mw": prototype_number(row.frp_mw),
                "confidence_native": row.confidence_native,
                "daynight": row.daynight,
                "brightness_k": prototype_number(row.brightness_native),
                "brightness_field": brightness_field,
                "source_id": str(row.source_id),
                "source_row": row.source_row,
            }
        )
    del rows
    source_ids = {r["source_id"] for r in records}
    sources = (
        session.execute(
            select(
                SourceFile.id,
                SourceFile.original_filename,
                SourceFile.sha256,
                SourceFile.source_url,
                SourceFile.sensor_code,
                SourceFile.product_version,
                SourceFile.processing_level,
            ).where(SourceFile.id.in_(source_ids))
        ).all()
        if source_ids
        else []
    )
    metadata = [
        {k: str(v) if isinstance(v, UUID) else v for k, v in row._mapping.items()}
        for row in sources
    ]
    return analyze_harmonization(query, records, sorted(metadata, key=lambda s: s["id"]))


def benchmark_text(folder: Path, name: str, manifest: dict):
    """Verify curated text exports, including Git's LF normalization of Windows exports."""
    content = (folder / name).read_bytes()
    expected = manifest["artifacts"][name]
    digest = hashlib.sha256(content).hexdigest()
    representation = "exact_bytes"
    if digest != expected:
        windows_bytes = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if hashlib.sha256(windows_bytes).hexdigest() != expected:
            raise ValueError(f"Benchmark checksum mismatch for {name}")
        representation = "manifest_matches_reconstructed_crlf_text"
    return content.decode("utf-8"), {
        "file": name,
        "sha256": digest,
        "manifest_sha256": expected,
        "verification": representation,
    }


def validation_evidence(study: str, split: str):
    """Replay fixed published candidates on their original blocked holdouts."""
    folder = VALIDATION_ROOT / study
    manifest = json.loads((folder / "summary-manifest.json").read_text(encoding="utf-8"))
    verified = []

    def read(name):
        content, metadata = benchmark_text(folder, name, manifest)
        verified.append(metadata)
        return content

    evaluation = json.loads(read("evaluation.json"))
    config = json.loads(read("protocol.json"))
    sources = json.loads(read("source-files.json"))["files"]
    geometry = json.loads(read("regions.geojson"))
    pairs = pd.read_csv(
        io.StringIO(read("all-pairs-including-missing.csv")), float_precision="round_trip"
    )
    predictions = pd.read_csv(
        io.StringIO(read("candidate-predictions.csv")), float_precision="round_trip"
    )
    method = evaluation["validation_selected_method"]
    model = json.loads(read(f"model-{method}.json"))
    core = {key: value for key, value in model.items() if key != "model_version"}
    if fingerprint(core) != model["model_version"] or model != evaluation["models"][method]:
        raise ValueError("Candidate content differs from its versioned model")
    candidate = predictions[predictions.method == method].copy().reset_index(drop=True)
    replay, _ = predict_model(model, candidate)
    if not np.allclose(replay, candidate.prediction.to_numpy(), rtol=1e-10, atol=1e-12):
        raise ValueError("Candidate prediction replay differs from the archived result")
    protocol = evaluation["protocol"]
    heldout = pairs.region_id.isin(protocol["heldout_regions"])
    if split == "test_regions":
        scope = heldout & pairs.year.isin(protocol["train_years"])
    elif split == "test_years_and_regions":
        scope = heldout & pairs.year.isin(protocol["test_years"])
    else:
        scope = ~heldout & pairs.year.isin(protocol["test_years"])
    calendar = pairs[scope].copy()
    sample = candidate[candidate.split == split].copy().reset_index(drop=True)
    before = metrics(sample.activity_reference, sample.activity_source)
    after = metrics(sample.activity_reference, sample.prediction)
    published = evaluation["evaluations"][method]["splits"][split]
    if before["n"] != after["n"] or after["n"] != published["n"]:
        raise ValueError("Holdout pair counts differ from the archived evaluation")
    if int(calendar.paired.sum()) != after["n"]:
        raise ValueError("Holdout calendar differs from the archived prediction scope")
    for name in ("mae", "rmse", "bias"):
        if after[name] is not None and not math.isclose(
            after[name], published[name], rel_tol=1e-10, abs_tol=1e-12
        ):
            raise ValueError("Recomputed agreement differs from the archived evaluation")
    trend = trend_metrics(sample, sample.prediction, protocol["min_trend_months"])
    season = seasonal_metrics(sample, sample.prediction)
    region_names = {
        str(feature["properties"]["region_id"]): feature["properties"].get(
            "name", str(feature["properties"]["region_id"])
        )
        for feature in geometry["features"]
    }
    regions = []
    for region_id, months in calendar.groupby("region_id", sort=True):
        months = months.sort_values("month")
        regional = sample[sample.region_id == region_id]
        estimates = regional.set_index("month").prediction.to_dict()
        regions.append(
            {
                "id": str(region_id),
                "label": region_names.get(str(region_id), str(region_id)),
                "labels": months.month.tolist(),
                "reference": [
                    float(value) if pd.notna(value) else None for value in months.activity_reference
                ],
                "source": [
                    float(value) if pd.notna(value) else None for value in months.activity_source
                ],
                "candidate": [
                    float(estimates[month]) if month in estimates else None
                    for month in months.month
                ],
                "baseline": metrics(regional.activity_reference, regional.activity_source),
                "calibrated": metrics(regional.activity_reference, regional.prediction),
            }
        )
    quarters = []
    for quarter, subset in sample.groupby((sample.month_number - 1) // 3 + 1):
        quarters.append(
            {
                "quarter": int(quarter),
                "baseline": metrics(subset.activity_reference, subset.activity_source),
                "candidate": metrics(subset.activity_reference, subset.prediction),
            }
        )
    reasons = list(evaluation["limitations_or_rejection_reasons"])
    if not season["available"]:
        reasons.append(f"{split}:seasonal_profile_not_estimable")
    elif season["profile_mae"] > season["baseline_profile_mae"] * 1.1 + 1e-12:
        reasons.append(f"{split}:seasonal_profile_error_worsened")
    calculation_code_sha256 = hashlib.sha256(
        (code_hash() + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()).encode()
    ).hexdigest()
    dependency_versions = {name: version(name) for name in ("numpy", "pandas")}
    identity = {
        "version": "harmonization-evidence-v1",
        "study": study,
        "split": split,
        "artifacts": verified,
        "calculation_code_sha256": calculation_code_sha256,
        "dependency_versions": dependency_versions,
    }
    return {
        "version": identity["version"],
        "analysis_id": fingerprint(identity),
        "calculation_code_sha256": calculation_code_sha256,
        "dependency_versions": dependency_versions,
        "study": study,
        "study_id": manifest["study_id"],
        "method": method,
        "model_version": model["model_version"],
        "split": split,
        "protocol": protocol,
        "start": config["start"],
        "end_exclusive": config["end"],
        "source_sensor": evaluation["source_sensor"],
        "reference_sensor": evaluation["reference_sensor"],
        "daynight": evaluation["daynight"],
        "grid_size_m": config["grid_size_m"],
        "metric": evaluation["metric"],
        "units": "reported flagged-cell days per 1,000 km² per month",
        "metrics": {
            "baseline": before,
            "candidate": after,
            "candidate_intervals_95": metric_intervals(
                sample, sample.prediction, protocol["bootstrap_repeats"], protocol["seed"]
            ),
        },
        "paired_bins": after["n"],
        "unpaired_bins": int((~calendar.paired).sum()),
        "calendar_bins": len(calendar),
        "regions": regions,
        "quarterly": quarters,
        "trend": trend,
        "seasonal_profile": season,
        "coverage_mode": "detection_only_conditional",
        "observation_coverage": "unknown",
        "operational_calibration_supported": False,
        "published_operational_calibration_supported": evaluation[
            "operational_calibration_supported"
        ],
        "limitations_or_rejection_reasons": sorted(set(reasons)),
        "selection_used_test_data": evaluation["selection_used_test_data"],
        "selection_rule": evaluation["selection_rule"],
        "source_files": sources,
        "artifacts": verified,
        "diagnostic_scope": (
            "Recomputed fixed-candidate holdouts and retrospective seasonal diagnostics "
            "from archived study inputs."
        ),
        "limitations": [
            "Agreement is conditional on paired detection-supported region-month bins "
            "and a MODIS Aqua reference.",
            "Common geography, calendar periods and the daytime stratum define the "
            "comparison against MODIS Aqua.",
            "Clouds, viewing geometry, overpass timing and detection sensitivity "
            "remain unmeasured confounders.",
            "Missing archive bins remain unknown. Valid non-detection opportunities "
            "require independently audited observation coverage.",
            "Seasonal diagnostics are retrospective. Quarterly support requires at least "
            "one paired month per quarter and at least three years.",
            "95% intervals use held-out year-block bootstrap of a fixed model "
            "and describe sample agreement variability.",
            "The 2013–2025 benchmark uses versioned 5 km equal-area activity. The live "
            "0.01-degree prototype and later archive extensions have their own scopes.",
        ],
    }


@router.get("/analytics/harmonization/validation")
def harmonization_validation(
    study: Literal["jordan", "levant"] = "jordan",
    split: Literal["test_years", "test_regions", "test_years_and_regions"] = "test_years",
):
    try:
        return validation_evidence(study, split)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            503, "Verified validation evidence is unavailable; check the bundled study artifacts"
        ) from error
