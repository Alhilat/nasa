"""Read-only dashboard comparisons of persisted aggregates with equivalent archive bins."""

import csv
import io
import json
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import and_, func, select
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
