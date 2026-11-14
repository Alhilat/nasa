"""Persistence models. Schema changes require an explicit Alembic migration."""

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    FetchedValue,
    LargeBinary,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Sensor(Base):
    __tablename__ = "sensors"

    code: Mapped[str] = mapped_column(primary_key=True)
    instrument: Mapped[str]
    platform: Mapped[str]
    nominal_resolution_m: Mapped[int]
    confidence_scheme: Mapped[str]
    metadata_url: Mapped[str]


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (UniqueConstraint(
        "sha256", "sensor_code", "product_version", "processing_level",
        name="uq_source_content_context",
    ),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str]
    original_filename: Mapped[str]
    source_url: Mapped[str]
    sensor_code: Mapped[str] = mapped_column(ForeignKey("sensors.code"))
    product_version: Mapped[str]
    processing_level: Mapped[str]
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    row_count: Mapped[int]
    original_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("source_id", "source_row"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_files.id"))
    source_row: Mapped[int]
    sensor_code: Mapped[str | None] = mapped_column(ForeignKey("sensors.code"))
    raw_properties: Mapped[dict[str, Any]] = mapped_column(JSONB)
    record_hash: Mapped[str] = mapped_column(server_default=FetchedValue())


class Observation(Base):
    __tablename__ = "normalized_observations"
    __table_args__ = (ForeignKeyConstraint(
        ["source_id", "source_row"], ["raw_records.source_id", "raw_records.source_row"],
    ),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[uuid.UUID]
    source_row: Mapped[int]
    sensor_code: Mapped[str] = mapped_column(ForeignKey("sensors.code"))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float]
    longitude: Mapped[float]
    location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
        Computed("ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)", persisted=True),
    )
    frp_mw: Mapped[float | None]
    confidence_native: Mapped[str]
    confidence_class: Mapped[str]
    daynight: Mapped[str | None]
    scan_km: Mapped[float | None]
    track_km: Mapped[float | None]
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSONB)
    record_hash: Mapped[str] = mapped_column(unique=True)


class ObservationRecord(Base):
    __tablename__ = "observation_records"
    raw_record_id: Mapped[int] = mapped_column(ForeignKey("raw_records.id"), primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("normalized_observations.id"))


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id"), primary_key=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_files.id"))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportCheckpoint(Base):
    __tablename__ = "import_checkpoints"
    stream_key: Mapped[str] = mapped_column(primary_key=True)
    next_date: Mapped[date]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="running")
    algorithm_version: Mapped[str]
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None]
    output_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class HarmonizedAggregate(Base):
    __tablename__ = "harmonized_aggregates"
    __table_args__ = (UniqueConstraint("job_id", "sensor_code", "day", "grid_x", "grid_y"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id"))
    sensor_code: Mapped[str] = mapped_column(ForeignKey("sensors.code"))
    day: Mapped[date]
    grid_x: Mapped[int]
    grid_y: Mapped[int]
    grid_size_deg: Mapped[float]
    cell: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False))
    detection_count: Mapped[int]
    frp_sum_mw: Mapped[float | None]
    frp_known_count: Mapped[int]
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AggregateSource(Base):
    __tablename__ = "aggregate_sources"
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id"), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_files.id"), primary_key=True)


class AnalyticalResult(Base):
    __tablename__ = "analytical_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id"))
    result_type: Mapped[str]
    method_version: Mapped[str]
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
