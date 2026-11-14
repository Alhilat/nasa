import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import repository
from app.catalog import SCIENCE_NOTES, SENSOR_CODES
from app.core.config import get_settings
from app.db import get_session
from app.models import (
    CalibrationModel, DataQualityReport, HarmonizedAggregate, Observation, ObservationRecord, ProcessingJob,
    RawRecord, Sensor, SourceFile,
)
from app.schemas import ObservationQuery

settings = get_settings()
app = FastAPI(title="FireScope API", version="0.1.0", docs_url="/docs")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
SessionDep = Annotated[Session, Depends(get_session)]
API = "/api/v1"


@app.exception_handler(SQLAlchemyError)
async def database_error(_request, exc):
    logging.getLogger(__name__).error("Database operation failed: %s", type(exc).__name__)
    return JSONResponse(status_code=503, content={
        "detail": "Database unavailable or schema not migrated. See startup instructions.",
    })


@app.get(f"{API}/health/live", tags=["operations"])
def liveness():
    return {"status": "ok", "service": "firescope-api", "version": "0.1.0"}


@app.get(f"{API}/health/ready", tags=["operations"])
def readiness(session: SessionDep):
    session.execute(text("SELECT PostGIS_Version()"))
    revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != "0003_calibration":
        raise HTTPException(503, "Database schema is not current")
    session.execute(select(Sensor.code).limit(1)).first()
    return {"status": "ready", "database": "connected", "schema_revision": revision}


@app.get(f"{API}/config", tags=["operations"])
def configuration():
    return {
        "name": "FireScope", "version": "0.1.0", "environment": settings.app_env,
        "crs": "EPSG:4326", "time_zone": "UTC", "sensor_codes": SENSOR_CODES,
        "max_query_results": min(settings.max_query_results, 5000),
        "features": {"polygon_query": True, "grid_aggregation": True, "statistical_calibration": True,
                     "anomalies": False, "forecasting": False, "machine_learning": False},
        "science_notes": SCIENCE_NOTES,
    }


def validate_sensors(query: ObservationQuery):
    if set(query.sensors) - set(SENSOR_CODES):
        raise HTTPException(422, "Unknown sensor code; consult /api/v1/config")
    return query


def get_query(
    bbox: str | None = None,
    start: str | None = None,
    end: str | None = None,
    sensors: Annotated[list[str] | None, Query()] = None,
    confidence: str | None = None,
    limit: int = 2000,
    offset: int = 0,
):
    try:
        query = ObservationQuery(
            bbox=tuple(float(x) for x in bbox.split(",")) if bbox else None,
            start=start, end=end, sensors=sensors or [], confidence=confidence,
            limit=limit, offset=offset,
        )
    except (ValidationError, ValueError) as exc:
        # Serialize validation errors without non-JSON exception objects in ctx.
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                  for e in exc.errors()] if isinstance(
            exc, ValidationError,
        ) else "bbox must be west,south,east,north"
        raise HTTPException(422, detail=detail) from exc
    return validate_sensors(query)


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc):
    return JSONResponse(status_code=422, content={
        "detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                   for e in exc.errors()],
    })


@app.get(f"{API}/sensors", tags=["catalog"])
def sensors(session: SessionDep):
    return [
        {"code": s.code, "instrument": s.instrument, "platform": s.platform,
         "nominal_resolution_m": s.nominal_resolution_m,
         "confidence_scheme": s.confidence_scheme, "metadata_url": s.metadata_url}
        for s in session.scalars(select(Sensor).where(Sensor.code.in_(SENSOR_CODES)).order_by(Sensor.code))
    ]


@app.get(f"{API}/observations", tags=["observations"])
def observations(session: SessionDep, query: Annotated[ObservationQuery, Depends(get_query)]):
    return repository.query_observations(session, query, settings.max_query_results)


@app.post(f"{API}/observations/query", tags=["observations"])
def polygon_observations(query: ObservationQuery, session: SessionDep):
    return repository.query_observations(session, validate_sensors(query), settings.max_query_results)


@app.get(f"{API}/observations/{{observation_id}}", tags=["observations"])
def observation_detail(observation_id: int, session: SessionDep):
    row = session.get(Observation, observation_id)
    if row is None:
        raise HTTPException(404, "Observation not found")
    source = session.get(SourceFile, row.source_id)
    raw = session.scalar(select(RawRecord).where(
        RawRecord.source_id == row.source_id, RawRecord.source_row == row.source_row,
    ))
    copies = session.execute(select(
        RawRecord.id, RawRecord.source_id, RawRecord.source_row, SourceFile.sha256,
    ).join(ObservationRecord, ObservationRecord.raw_record_id == RawRecord.id).join(
        SourceFile, SourceFile.id == RawRecord.source_id,
    ).where(ObservationRecord.observation_id == row.id).order_by(RawRecord.id)).all()
    return {
        "id": row.id, "raw_properties": raw.raw_properties, "uncertainty": row.uncertainty,
        "source_id": row.source_id, "source_row": row.source_row,
        "source_url": source.source_url, "source_sha256": source.sha256,
        "product_version": source.product_version, "processing_level": source.processing_level,
        "retrieved_at": source.retrieved_at,
        "record_hash": row.record_hash,
        "source_copies": [{"raw_record_id": r.id, "source_id": r.source_id,
                           "source_row": r.source_row, "sha256": r.sha256} for r in copies],
    }


@app.post(f"{API}/analytics/summary", tags=["analytics"])
def summary(query: ObservationQuery, session: SessionDep):
    return repository.summarize(session, validate_sensors(query))


@app.get(f"{API}/sources", tags=["provenance"])
def sources(session: SessionDep, limit: int = Query(50, ge=1, le=200),
            offset: int = Query(0, ge=0)):
    rows = session.scalars(select(SourceFile).order_by(
        SourceFile.imported_at.desc(), SourceFile.id,
    ).offset(offset).limit(limit + 1)).all()
    return {"items": [{
        "id": s.id, "sha256": s.sha256, "original_filename": s.original_filename,
        "sensor_code": s.sensor_code, "source_url": s.source_url,
        "product_version": s.product_version, "processing_level": s.processing_level,
        "retrieved_at": s.retrieved_at, "imported_at": s.imported_at, "row_count": s.row_count,
        "source_metadata": s.source_metadata,
    } for s in rows[:limit]], "has_more": len(rows) > limit}


@app.get(f"{API}/jobs", tags=["processing"])
def jobs(session: SessionDep, limit: int = Query(50, ge=1, le=200)):
    return [{
        "id": j.id, "kind": j.kind, "status": j.status, "algorithm_version": j.algorithm_version,
        "parameters": j.parameters, "started_at": j.started_at, "finished_at": j.finished_at,
        "error_message": j.error_message, "output_metadata": j.output_metadata,
    } for j in session.scalars(select(ProcessingJob).order_by(
        ProcessingJob.started_at.desc(), ProcessingJob.id,
    ).limit(limit))]


@app.get(f"{API}/quality-reports/{{job_id}}", tags=["provenance"])
def quality_report(job_id: UUID, session: SessionDep):
    report = session.get(DataQualityReport, job_id)
    if not report:
        raise HTTPException(404, "Data-quality report not found")
    return {"job_id": report.job_id, "source_id": report.source_id, "report": report.report}


@app.get(f"{API}/calibration-models/{{model_version}}", tags=["analytics"])
def calibration_model(model_version: str, session: SessionDep):
    if len(model_version) != 64 or any(c not in "0123456789abcdef" for c in model_version):
        raise HTTPException(422, "Model version must be a SHA-256 identifier")
    model = session.get(CalibrationModel, model_version)
    if model is None:
        raise HTTPException(404, "Calibration model not found")
    return {"model_version": model.model_version, "method": model.method, "status": model.status,
            "artifact": model.artifact, "validation": model.validation,
            "input_manifest": model.input_manifest}


@app.get(f"{API}/aggregates/{{job_id}}", tags=["analytics"])
def aggregates(job_id: UUID, session: SessionDep, limit: int = Query(1000, ge=1, le=5000),
               offset: int = Query(0, ge=0)):
    job = session.get(ProcessingJob, job_id)
    if not job or job.kind != "aggregate" or job.status != "succeeded":
        raise HTTPException(404, "Successful aggregate job not found")
    rows = session.execute(select(
        HarmonizedAggregate, func.ST_AsGeoJSON(HarmonizedAggregate.cell),
    ).where(HarmonizedAggregate.job_id == job_id).order_by(
        HarmonizedAggregate.day, HarmonizedAggregate.id,
    ).offset(offset).limit(limit + 1)).all()
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": json.loads(geometry),
        "properties": {"sensor_code": a.sensor_code, "day": a.day,
                       "detection_count": a.detection_count, "frp_sum_mw": a.frp_sum_mw,
                       "frp_known_count": a.frp_known_count, "grid_size_deg": a.grid_size_deg,
                       "uncertainty": a.uncertainty},
    } for a, geometry in rows[:limit]],
        "metadata": {"job_id": job_id, "has_more": len(rows) > limit,
                     "parameters": job.parameters, "provenance": job.output_metadata}}
