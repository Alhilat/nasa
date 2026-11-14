"""Unpaginated, bounded historical selection and deterministic export endpoints."""

from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.history import HistoryQuery, analyze, calendar_csv
from app.models import Observation, ObservationRecord, RawRecord, SourceFile
from app.repository import observation_filters
from app.schemas import ObservationQuery

router = APIRouter(prefix="/api/v1/analytics/history", tags=["historical intelligence"])
SessionDep = Annotated[Session, Depends(get_session)]
MAX_RECORDS = 250000


def load_inputs(
    session: Session,
    query: HistoryQuery,
    max_records: int | None = None,
    selection: ObservationQuery | None = None,
):
    max_records = MAX_RECORDS if max_records is None else min(MAX_RECORDS, max_records)
    conditions = observation_filters(
        selection if selection is not None else query.observation_query()
    )
    rows = session.execute(
        select(
            Observation.id,
            Observation.sensor_code,
            Observation.acquired_at,
            Observation.latitude,
            Observation.longitude,
            Observation.record_hash,
            Observation.source_id,
            Observation.confidence_class,
        )
        .where(*conditions)
        .order_by(Observation.id)
        .limit(max_records + 1)
    ).all()
    if len(rows) > max_records:
        raise HTTPException(
            413, f"Selection exceeds {max_records:,} observations; narrow the area/years"
        )
    copies = session.execute(
        select(ObservationRecord.observation_id, RawRecord.source_id)
        .join(
            RawRecord,
            RawRecord.id == ObservationRecord.raw_record_id,
        )
        .join(Observation, Observation.id == ObservationRecord.observation_id)
        .where(*conditions)
    ).all()
    links = {r.id: {str(r.source_id)} for r in rows}
    for observation_id, source_id in copies:
        if observation_id in links:
            links[observation_id].add(str(source_id))
    source_ids = {s for ids in links.values() for s in ids}
    # Never load original_bytes; historical exports include metadata and checksums only.
    sources = []
    source_ids = sorted(source_ids)
    for offset in range(0, len(source_ids), 1000):
        sources.extend(
            session.execute(
                select(
                    SourceFile.id,
                    SourceFile.sha256,
                    SourceFile.original_filename,
                    SourceFile.source_url,
                    SourceFile.sensor_code,
                    SourceFile.product_version,
                    SourceFile.processing_level,
                    SourceFile.retrieved_at,
                    SourceFile.imported_at,
                    SourceFile.row_count,
                    SourceFile.source_metadata,
                ).where(SourceFile.id.in_(source_ids[offset : offset + 1000]))
            ).all()
        )
    records = [
        {
            "id": r.id,
            "sensor_code": r.sensor_code,
            "acquired_at": r.acquired_at.astimezone(UTC).isoformat(),
            "latitude": r.latitude,
            "longitude": r.longitude,
            "record_hash": r.record_hash,
            "confidence_class": r.confidence_class,
            "source_ids": sorted(links[r.id]),
        }
        for r in rows
    ]
    metadata = [
        {
            k: (
                v.astimezone(UTC).isoformat()
                if hasattr(v, "isoformat")
                else str(v)
                if isinstance(v, UUID)
                else v
            )
            for k, v in row._mapping.items()
        }
        for row in sources
    ]
    return records, metadata


def load_history(session: Session, query: HistoryQuery, max_records: int | None = None):
    return analyze(query, *load_inputs(session, query, max_records))


@router.post("")
def historical_intelligence(query: HistoryQuery, session: SessionDep):
    return load_history(session, query)


@router.post("/export.csv", response_class=Response)
def export_calendar(query: HistoryQuery, session: SessionDep):
    result = load_history(session, query)
    return Response(
        calendar_csv(result),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="firescope-history.csv"',
            "X-Analysis-ID": result["analysis_id"],
        },
    )
