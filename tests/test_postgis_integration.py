"""Real PostGIS tests in a fresh owned schema; requires TEST_DATABASE_URL.

All observations in this module are synthetic software fixtures, never NASA data.
"""

import argparse
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db import get_session
from app.main import app
from app.models import (
    DataQualityReport, ImportCheckpoint, Observation, ObservationRecord, ProcessingJob,
    RawRecord, SourceFile,
)
from firescope_pipeline import cli
from firescope_pipeline.ingest import IngestionRejected
from firescope_pipeline.selection import Selection
from firescope_pipeline.service import import_source

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def factory():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; PostGIS integration checks require a database")
    admin_engine = create_engine(url)
    schema = "firescope_test_" + uuid.uuid4().hex
    with admin_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public"))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def search_path(dbapi_connection, _record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}", public')
        dbapi_connection.commit()

    try:
        with engine.begin() as connection:
            config = Config(str(Path(__file__).parents[1] / "backend" / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            # Only this fixture's UUID-named schema is removed. No existing schema is touched.
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture(scope="module")
def imported(factory, tmp_path_factory):
    path = tmp_path_factory.mktemp("synthetic") / "test-only.csv"
    path.write_text(
        "latitude,longitude,acq_date,acq_time,satellite,confidence,frp,version\n"
        "0,0,2024-01-01,0030,Terra,80,,6.1\n"
        "1,1,2024-01-01,0130,Terra,30,5,6.1\n"
        "0,179,2024-01-02,0030,Terra,80,2,6.1\n"
        "0,-179,2024-01-02,0030,Terra,80,3,6.1\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        file=str(path), sensor="MODIS_TERRA", source_url="https://example.org/test-only",
        product_version="6.1", processing_level="standard",
        retrieved_at=datetime(2024, 1, 3, tzinfo=UTC),
    )
    original = cli.session_factory
    cli.session_factory = lambda: factory
    try:
        first = cli.ingest(args)
        second = cli.ingest(args)
    finally:
        cli.session_factory = original
    assert not first["already_imported"]
    assert second["already_imported"]
    return first, args, path


@pytest.fixture
def db_client(factory):
    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_real_queries_boundaries_wrapping_and_summary(factory, imported, db_client):
    response = db_client.get("/api/v1/observations?bbox=0,0,1,1")
    assert response.status_code == 200
    assert len(response.json()["features"]) == 2  # Inclusive polygon/bbox boundaries.
    wrapped = db_client.get("/api/v1/observations?bbox=170,-10,-170,10").json()
    assert len(wrapped["features"]) == 2
    summary = db_client.post("/api/v1/analytics/summary", json={}).json()
    assert summary["detection_count"] == 4
    assert summary["frp_known_count"] == 3
    assert sum(row["count"] for row in summary["daily"]) == 4
    limited = db_client.get("/api/v1/observations?limit=1").json()
    assert limited["metadata"]["has_more"]
    assert len(limited["features"]) == 1
    first_id = limited["features"][0]["properties"]["id"]
    assert db_client.get(f"/api/v1/observations/{first_id}").json()["source_row"] == 1
    assert db_client.get("/api/v1/health/ready").status_code == 200


def test_real_polygon_hole(imported, db_client):
    polygon = {"type": "Polygon", "coordinates": [
        [[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]],
        [[-0.5, -0.5], [-0.5, 0.5], [0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]],
    ]}
    response = db_client.post("/api/v1/observations/query", json={"polygon": polygon})
    assert response.status_code == 200
    assert len(response.json()["features"]) == 1
    assert response.json()["features"][0]["geometry"]["coordinates"] == [1, 1]


def test_archive_is_exact_and_immutable(factory, imported):
    first, _args, path = imported
    with factory() as session:
        source = session.get(SourceFile, uuid.UUID(first["source_id"]))
        assert source.original_bytes == path.read_bytes()
        assert session.scalar(select(func.count()).select_from(Observation)) == 4
    for sql in (
        "UPDATE raw_records SET raw_properties='{}'",
        "DELETE FROM raw_records", "TRUNCATE raw_records CASCADE",
        "UPDATE normalized_observations SET confidence_native='0'",
        "UPDATE source_files SET source_url='https://example.org/changed'",
    ):
        with pytest.raises(DBAPIError, match="immutable"), factory.begin() as session:
            session.execute(text(sql))


def test_invalid_import_rolls_back_and_records_failed_job(factory, imported, tmp_path, monkeypatch):
    _first, args, path = imported
    broken = tmp_path / "test-only-invalid.csv"
    broken.write_bytes(path.read_bytes().replace(b"1,1,2024", b"91,1,2024"))
    monkeypatch.setattr(cli, "session_factory", lambda: factory)
    invalid = argparse.Namespace(**{**vars(args), "file": str(broken)})
    with pytest.raises(ValueError, match="Data row 2"):
        cli.ingest(invalid)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceFile)) == 1
        assert session.scalar(select(func.count()).select_from(Observation)) == 4
        assert session.scalar(select(func.count()).select_from(ProcessingJob).where(
            ProcessingJob.status == "failed",
        )) == 1


def test_aggregate_lineage_and_unknown_frp(factory, imported, db_client, monkeypatch):
    monkeypatch.setattr(cli, "session_factory", lambda: factory)
    result = cli.aggregate(argparse.Namespace(
        start=datetime(2024, 1, 1, tzinfo=UTC), end=datetime(2024, 1, 3, tzinfo=UTC),
        grid_size=0.25,
    ))
    assert result["input_rows"] == 4
    assert result["source_ids"] == [imported[0]["source_id"]]
    response = db_client.get(f'/api/v1/aggregates/{result["job_id"]}')
    assert response.status_code == 200
    features = response.json()["features"]
    assert sum(f["properties"]["detection_count"] for f in features) == 4
    assert any(f["properties"]["frp_sum_mw"] is None for f in features)


def import_test_content(factory, content, **kwargs):
    return import_source(
        factory, content, filename="synthetic-test-only.csv", sensor="MODIS",
        product_version="6.1", processing_level="standard",
        source_url="https://example.org/synthetic-test-only",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC), **kwargs,
    )


def test_overlapping_exports_link_all_raw_copies_to_one_normalized(factory):
    header = b"latitude,longitude,acq_date,acq_time,satellite,confidence,frp,version\n"
    row = b"31,36,2025-03-01,0030,T,80,7,6.1\n"
    first = import_test_content(factory, header + row + row)
    # Distinct bytes, identical parsed payload: newlines do not change record identity.
    second = import_test_content(factory, (header + row).replace(b"\n", b"\r\n"))
    assert first["report"]["normalized_inserted"] == 1
    assert second["report"]["normalized_inserted"] == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RawRecord).where(
            RawRecord.source_id.in_([uuid.UUID(first["source_id"]), uuid.UUID(second["source_id"])]),
        )) == 3
        observation = session.scalar(select(Observation).where(
            Observation.acquired_at == datetime(2025, 3, 1, 0, 30, tzinfo=UTC),
        ))
        assert session.scalar(select(func.count()).select_from(ObservationRecord).where(
            ObservationRecord.observation_id == observation.id,
        )) == 3
        raw = session.get(RawRecord, session.scalar(select(ObservationRecord.raw_record_id).where(
            ObservationRecord.observation_id == observation.id,
        ).limit(1)))
        assert raw.record_hash == observation.record_hash


def test_reimporting_same_file_with_wider_filter_adds_only_missing_records(factory):
    content = (b"latitude,longitude,acq_date,acq_time,satellite,confidence,version\n"
               b"31,36,2025-04-01,0030,T,80,6.1\n"
               b"32,37,2025-04-02,0030,T,80,6.1\n")
    first = import_test_content(factory, content, selection=Selection(bbox=(35, 30, 36.5, 31.5)))
    second = import_test_content(factory, content)
    third = import_test_content(factory, content)
    assert first["report"]["raw_inserted"] == 2
    assert first["report"]["normalized_inserted"] == 1
    assert second["source_id"] == first["source_id"]
    assert second["report"]["raw_inserted"] == 0
    assert second["report"]["normalized_inserted"] == 1
    assert third["already_imported"]
    assert third["report"]["normalized_inserted"] == 0


def test_quarantine_keeps_invalid_raw_and_strict_failure_has_quality_report(factory):
    content = (b"latitude,longitude,acq_date,acq_time,satellite,confidence,version\n"
               b"31,36,2025-05-01,0030,T,80,6.1\n"
               b"91,36,2025-05-01,0030,T,80,6.1\n")
    with pytest.raises(IngestionRejected):
        import_test_content(factory, content)
    with factory() as session:
        assert session.scalar(select(DataQualityReport).join(ProcessingJob).where(
            ProcessingJob.status == "failed", DataQualityReport.report["invalid_rows"].as_integer() == 1,
        ).limit(1)) is not None
    result = import_test_content(factory, content, on_error="quarantine")
    assert result["report"]["invalid_rows"] == 1
    assert result["report"]["raw_inserted"] == 2
    assert result["report"]["normalized_inserted"] == 1


def test_empty_api_payload_checkpoints_are_context_specific_and_atomic(factory):
    content = b"latitude,longitude,acq_date,acq_time,satellite,confidence,version\n"
    for sensor, source in [("VIIRS_SNPP", "VIIRS_SNPP_NRT"), ("VIIRS_NOAA20", "VIIRS_NOAA20_NRT")]:
        result = import_source(
            factory, content, filename="synthetic-empty-response.csv", sensor=sensor,
            product_version="native", processing_level="nrt",
            source_url="https://example.org/synthetic-api", retrieved_at=datetime.now(UTC),
            checkpoint={"stream_key": source, "next_date": datetime(2025, 6, 2).date(),
                        "parameters": {"source": source}},
        )
        assert result["report"]["normalized_inserted"] == 0
        with factory() as session:
            assert session.get(ImportCheckpoint, source).next_date.isoformat() == "2025-06-02"
    invalid = content + b"91,36,2025-06-02,0030,N,h,2.0NRT\n"
    with pytest.raises(IngestionRejected):
        import_source(
            factory, invalid, filename="synthetic-invalid.csv", sensor="VIIRS_SNPP",
            product_version="native", processing_level="nrt",
            source_url="https://example.org/synthetic-api", retrieved_at=datetime.now(UTC),
            checkpoint={"stream_key": "VIIRS_SNPP_NRT", "next_date": datetime(2025, 6, 3).date(),
                        "parameters": {}},
        )
    with factory() as session:
        assert session.get(ImportCheckpoint, "VIIRS_SNPP_NRT").next_date.isoformat() == "2025-06-02"


def test_changed_measurement_and_processing_versions_are_not_merged(factory):
    header = b"latitude,longitude,acq_date,acq_time,satellite,confidence,frp,version\n"
    row = b"31,36,2025-07-01,0030,T,80,7,6.1\n"
    first = import_test_content(factory, header + row)
    changed = import_test_content(factory, header + row.replace(b",7,", b",8,"))
    nrt = import_source(
        factory, header + row.replace(b"6.1", b"6.1NRT"), filename="synthetic-nrt.csv",
        sensor="MODIS", product_version="6.1NRT", processing_level="nrt",
        source_url="https://example.org/synthetic-nrt", retrieved_at=datetime.now(UTC),
    )
    assert all(result["report"]["normalized_inserted"] == 1 for result in (first, changed, nrt))
