"""Transactional archiving, canonical records, provenance links and checkpoints."""
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.models import (
    DataQualityReport, ImportCheckpoint, Observation, ObservationRecord, RawRecord, SourceFile,
)
from firescope_pipeline.ingest import (
    ALGORITHM_VERSION, IngestionRejected, checksum, inspect_csv,
)
from firescope_pipeline.jobs import run_job
from firescope_pipeline.selection import Selection


def import_source(factory, content: bytes, *, filename: str, sensor: str, product_version: str,
                  processing_level: str, source_url: str, retrieved_at: datetime,
                  selection: Selection | None = None, on_error="reject", metadata=None,
                  checkpoint: dict | None = None):
    parsed = urlparse(source_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("Use a public HTTPS source URL without credentials, query or fragment")
    if any(part in parsed.path for part in (
        "/api/area/csv/", "/api/country/csv/", "/api/data_availability/csv/",
    )):
        raise ValueError("Use the public source page, not a key-bearing FIRMS API URL")
    if retrieved_at.utcoffset() is None:
        raise ValueError("Retrieval time must include a timezone")
    if processing_level not in {"standard", "nrt"} or on_error not in {"reject", "quarantine"}:
        raise ValueError("Invalid processing level or invalid-row policy")
    digest = checksum(content)
    selection = selection or Selection()
    parameters = {"sha256": digest, "sensor_code": sensor, "product_version": product_version,
                  "processing_level": processing_level, "source_url": source_url,
                  "filters": selection.as_dict(), "on_error": on_error,
                  "retrieved_at": retrieved_at.isoformat(), "request_metadata": metadata or {}}

    def operation(session, job_id):
        try:
            batch = inspect_csv(content, sensor, product_version, selection, processing_level)
        except ValueError as exc:
            raise IngestionRejected({
                "report_version": "firms-quality-v1", "source_sha256": digest,
                "source_rows": None, "invalid_rows": None, "status": "rejected",
                "file_error": str(exc), "issue_samples": [{"message": str(exc)}],
            }) from exc
        if batch.report["invalid_rows"] and on_error == "reject":
            raise IngestionRejected(batch.report)
        # Local operator throughput is serialized to make import counts and checkpoint advancement
        # deterministic. Unique constraints also protect canonical identities across clients.
        session.execute(text("SELECT pg_advisory_xact_lock(724591830219)"))
        source = session.scalar(select(SourceFile).where(
            SourceFile.sha256 == digest, SourceFile.sensor_code == sensor,
            SourceFile.product_version == product_version,
            SourceFile.processing_level == processing_level,
        ))
        existing_source = source is not None
        if source:
            for key in ("sensor_code", "product_version", "processing_level"):
                if getattr(source, key) != parameters[key]:
                    raise ValueError("Same file already archived with different product metadata")
        else:
            source = SourceFile(
                sha256=digest, original_filename=filename, source_url=source_url,
                sensor_code=sensor, product_version=product_version, processing_level=processing_level,
                retrieved_at=retrieved_at, row_count=len(batch.raw), original_bytes=content,
                source_metadata={
                    "format": "NASA FIRMS CSV", "parser_version": ALGORITHM_VERSION,
                    "authenticity_verified": False,
                    "attribution": "NASA FIRMS / EOSDIS; source location retained",
                    "deduplication": "exact full payload + sensor + native version + processing level",
                    **(metadata or {}),
                },
            )
            session.add(source)
            session.flush()
        raw_inserted = 0
        for start in range(0, len(batch.raw), 1000):
            statement = insert(RawRecord).values([
                {"source_id": source.id, **row} for row in batch.raw[start:start + 1000]
            ]).on_conflict_do_nothing(index_elements=["source_id", "source_row"]).returning(RawRecord.id)
            raw_inserted += len(session.execute(statement).all())
        raw_records = {row.source_row: row for row in session.execute(select(
            RawRecord.source_row, RawRecord.id, RawRecord.record_hash,
        ).where(RawRecord.source_id == source.id))}
        normalized_inserted = 0
        for start in range(0, len(batch.selected), 1000):
            selected = batch.selected[start:start + 1000]
            unique = {}
            for row in selected:
                record_hash = raw_records[row["source_row"]].record_hash
                unique.setdefault(record_hash, {"source_id": source.id,
                                               "record_hash": record_hash, **row})
            statement = insert(Observation).values(list(unique.values())).on_conflict_do_nothing(
                index_elements=["record_hash"],
            ).returning(Observation.id)
            normalized_inserted += len(session.execute(statement).all())
            identities = dict(session.execute(select(Observation.record_hash, Observation.id).where(
                Observation.record_hash.in_(list(unique)),
            )).all())
            links = [{"raw_record_id": raw_records[row["source_row"]].id,
                      "observation_id": identities[raw_records[row["source_row"]].record_hash]}
                     for row in selected]
            session.execute(insert(ObservationRecord).values(links).on_conflict_do_nothing())
        report = {
            **batch.report, "status": "quarantined" if batch.report["invalid_rows"] else "imported",
            "raw_inserted": raw_inserted, "normalized_inserted": normalized_inserted,
            "selected_existing_or_duplicate": len(batch.selected) - normalized_inserted,
            "source_id": str(source.id), "job_id": str(job_id),
            "deduplication_policy": "exact payload only; changed values and NRT/standard retained",
        }
        session.add(DataQualityReport(job_id=job_id, source_id=source.id, report=report))
        if checkpoint:
            if batch.report["invalid_rows"]:
                raise ValueError("Cannot advance an API checkpoint with invalid records")
            existing = session.get(ImportCheckpoint, checkpoint["stream_key"])
            if not existing or existing.next_date < checkpoint["next_date"]:
                session.execute(insert(ImportCheckpoint).values(
                    **checkpoint, last_job_id=job_id, updated_at=datetime.now(UTC),
                ).on_conflict_do_update(index_elements=["stream_key"], set_={
                    "next_date": checkpoint["next_date"], "last_job_id": job_id,
                    "parameters": checkpoint["parameters"], "updated_at": datetime.now(UTC),
                }))
        return {"source_id": str(source.id), "sha256": digest, "rows": len(batch.selected),
                "already_imported": existing_source and normalized_inserted == 0, "report": report}

    return run_job(factory, "ingest", ALGORITHM_VERSION, parameters, operation)
