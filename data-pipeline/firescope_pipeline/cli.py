import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, insert, select
from sqlalchemy.exc import SQLAlchemyError

from app.db import session_factory
from app.models import (
    AggregateSource, HarmonizedAggregate, Observation, ObservationRecord, RawRecord,
)
from app.schemas import ObservationQuery
from firescope_pipeline.harmonize import ALGORITHM_VERSION as GRID_VERSION
from firescope_pipeline.harmonize import aggregate_frame, validate_grid
from firescope_pipeline.ingest import MAX_FILE_BYTES, SOURCE_SENSORS, inspect_csv
from firescope_pipeline.firms_api import API_SOURCES, FIRMSAPIError, FIRMSClient
from firescope_pipeline.selection import Selection, JORDAN_BBOX, JORDAN_START, JORDAN_END
from firescope_pipeline.service import import_source
from firescope_pipeline.sync import sync_api
from firescope_pipeline.jobs import run_job


def utc_timestamp(value: str):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use an ISO-8601 timestamp with timezone") from exc
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("Timestamp must include timezone (use Z for UTC)")
    return parsed.astimezone(UTC)


def selection_from_args(args, *, historical=True):
    profile = getattr(args, "profile", None)
    bbox = getattr(args, "bbox", None)
    polygon_file = getattr(args, "polygon", None)
    polygon = json.loads(Path(polygon_file).read_text(encoding="utf-8")) if polygon_file else None
    start, end = getattr(args, "start", None), getattr(args, "end", None)
    if profile == "jordan":
        bbox = bbox or JORDAN_BBOX
        if historical:
            start = start or utc_timestamp(JORDAN_START)
            end = end or utc_timestamp(JORDAN_END)
    return Selection(bbox=bbox, polygon=polygon, start=start if historical else None,
                     end=end if historical else None)


def ingest(args):
    path = Path(args.file)
    with path.open("rb") as stream:
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("File exceeds 50 MiB; split it before import")
    return import_source(
        session_factory(), content, filename=path.name, sensor=args.sensor,
        product_version=args.product_version, processing_level=args.processing_level,
        source_url=args.source_url, retrieved_at=args.retrieved_at,
        selection=selection_from_args(args), on_error=getattr(args, "on_error", "reject"),
    )


def aggregate(args):
    validate_grid(args.grid_size)
    query = ObservationQuery(start=args.start, end=args.end)
    parameters = {
        "start": query.start.isoformat(), "end": query.end.isoformat(),
        "grid_size_deg": args.grid_size, "crs": "EPSG:4326", "time_zone": "UTC",
        "sensor_stratified": True, "bias_corrected": False,
    }

    def operation(session, job_id):
        # One SELECT gives a consistent input snapshot, including exact source lineage.
        records = session.execute(select(
            Observation.id, Observation.sensor_code,
            Observation.acquired_at, Observation.latitude, Observation.longitude, Observation.frp_mw,
            func.array_agg(func.distinct(RawRecord.source_id)).label("source_ids"),
        ).join(ObservationRecord, ObservationRecord.observation_id == Observation.id).join(
            RawRecord, RawRecord.id == ObservationRecord.raw_record_id,
        ).where(Observation.acquired_at >= query.start, Observation.acquired_at < query.end).group_by(
            Observation.id,
        ).order_by(Observation.id).limit(1000001)).all()
        if len(records) > 1000000:
            raise ValueError("Aggregation exceeds 1 million rows; use a shorter time range")
        frame = pd.DataFrame([row._mapping for row in records])
        result = aggregate_frame(frame, args.grid_size)
        source_ids = sorted({str(source) for row in records for source in row.source_ids})
        if source_ids:
            session.execute(insert(AggregateSource), [
                {"job_id": job_id, "source_id": source_id} for source_id in source_ids
            ])
        output = []
        for row in result.itertuples():
            output.append({
                "job_id": job_id, "sensor_code": row.sensor_code, "day": row.day,
                "grid_x": row.grid_x, "grid_y": row.grid_y, "grid_size_deg": args.grid_size,
                "cell": WKTElement(row.geometry.wkt, srid=4326),
                "detection_count": row.detection_count, "frp_known_count": row.frp_known_count,
                "frp_sum_mw": None if pd.isna(row.frp_sum_mw) else float(row.frp_sum_mw),
                "uncertainty": {
                    "quantitative_uncertainty": None, "coverage_known": False,
                    "flags": ["sensor_bias_uncorrected", "distinct_observations_retained",
                              "angular_cells_not_equal_area", "not_burned_area"],
                },
            })
        for start in range(0, len(output), 2000):
            session.execute(insert(HarmonizedAggregate), output[start:start + 2000])
        return {"input_rows": len(records), "aggregate_rows": len(output),
                "source_ids": source_ids, "method": GRID_VERSION}

    return run_job(session_factory(), "aggregate", GRID_VERSION, parameters, operation)


def add_spatial_arguments(parser, *, historical=True):
    parser.add_argument("--profile", choices=["jordan"], help="Jordan study envelope; not a border polygon")
    parser.add_argument("--bbox", type=parse_bbox, help="west,south,east,north (WGS84)")
    parser.add_argument("--polygon", help="Path to a WGS84 Polygon/MultiPolygon GeoJSON geometry")
    if historical:
        parser.add_argument("--start", type=utc_timestamp, help="Inclusive timezone-aware timestamp")
        parser.add_argument("--end", type=utc_timestamp, help="Exclusive timezone-aware timestamp")
    parser.add_argument("--report", help="Write a machine-readable JSON quality report")


def parse_bbox(value):
    try:
        parts = tuple(float(x) for x in value.split(","))
        return ObservationQuery(bbox=parts).bbox
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use valid west,south,east,north coordinates") from exc


def write_report(path, report):
    if path:
        import tempfile
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         suffix=".json", delete=False) as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            temporary = Path(stream.name)
        temporary.replace(target)


def main():
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="FireScope reproducible NASA FIRMS processing")
    commands = parser.add_subparsers(dest="command", required=True)
    import_parser = commands.add_parser("ingest", help="Archive official historical FIRMS CSVs")
    import_parser.add_argument("file")
    import_parser.add_argument("--sensor", choices=SOURCE_SENSORS, required=True)
    import_parser.add_argument("--source-url", required=True)
    import_parser.add_argument("--product-version", required=True)
    import_parser.add_argument("--processing-level", choices=["nrt", "standard"], required=True)
    import_parser.add_argument("--retrieved-at", type=utc_timestamp, required=True)
    import_parser.add_argument("--on-error", choices=["reject", "quarantine"], default="reject")
    add_spatial_arguments(import_parser)
    validation = commands.add_parser("validate", help="Validate and report without a database")
    validation.add_argument("file")
    validation.add_argument("--sensor", choices=SOURCE_SENSORS, required=True)
    validation.add_argument("--product-version", required=True)
    add_spatial_arguments(validation)
    api_parser = commands.add_parser("sync-api", help="Import bounded FIRMS API date windows")
    api_parser.add_argument("--source", choices=sorted(API_SOURCES), required=True)
    api_parser.add_argument("--start", type=date.fromisoformat, required=True)
    api_parser.add_argument("--end", type=date.fromisoformat, required=True, help="Exclusive date")
    api_parser.add_argument("--resume", action="store_true")
    api_parser.add_argument("--lookback-days", type=int, default=2)
    api_parser.add_argument("--max-requests", type=int, default=200)
    api_parser.add_argument("--retries", type=int, default=3)
    add_spatial_arguments(api_parser, historical=False)
    grid_parser = commands.add_parser("aggregate", help="Create sensor/day/grid aggregates")
    grid_parser.add_argument("--start", type=utc_timestamp, required=True)
    grid_parser.add_argument("--end", type=utc_timestamp, required=True)
    grid_parser.add_argument("--grid-size", type=float, default=0.25)
    study_parser = commands.add_parser("harmonize", help="Evaluate statistical sensor-calibration candidates")
    study_parser.add_argument("--manifest", required=True)
    study_parser.add_argument("--regions", required=True)
    study_parser.add_argument("--protocol", required=True)
    study_parser.add_argument("--output", required=True)
    study_parser.add_argument("--exposure", help="Optional curated common-cell-day observability CSV")
    prepare_parser = commands.add_parser("prepare-jordan", help="Download official overlapping Jordan history")
    prepare_parser.add_argument("--output", default="data/harmonization/jordan")
    prepare_parser.add_argument("--start-year", type=int, default=2013)
    prepare_parser.add_argument("--end-year", type=int, default=2025)
    levant_parser = commands.add_parser("prepare-levant", help="Prepare a separate Jordan/Syria/Lebanon transfer benchmark")
    levant_parser.add_argument("--output", default="data/harmonization/levant")
    levant_parser.add_argument("--start-year", type=int, default=2013)
    levant_parser.add_argument("--end-year", type=int, default=2025)
    register_parser = commands.add_parser("register-calibration", help="Register a verified study bundle in PostGIS")
    register_parser.add_argument("bundle")
    args = parser.parse_args()
    try:
        if args.command == "harmonize":
            from firescope_pipeline.calibration.runner import run_study
            output = run_study(args.manifest, args.regions, args.protocol, args.output,
                               exposure_path=args.exposure)
        elif args.command in {"prepare-jordan", "prepare-levant"}:
            from firescope_pipeline.calibration.prepare import prepare_jordan
            output = prepare_jordan(args.output, args.start_year, args.end_year,
                                    include_levant=args.command == "prepare-levant")
        elif args.command == "register-calibration":
            from firescope_pipeline.calibration.io import register_bundle
            output = register_bundle(session_factory(), args.bundle)
        elif args.command == "ingest":
            output = ingest(args)
        elif args.command == "validate":
            with Path(args.file).open("rb") as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            batch = inspect_csv(content, args.sensor, args.product_version, selection_from_args(args))
            output = batch.report
            write_report(args.report, output)
            print(json.dumps(output, indent=2))
            if output["invalid_rows"]:
                parser.exit(1, "Validation failed; inspect the quality report\n")
            return
        elif args.command == "sync-api":
            with FIRMSClient(os.getenv("MAP_KEY", ""), retries=args.retries,
                             max_requests=args.max_requests) as client:
                output = sync_api(
                    session_factory(), client, source=args.source,
                    selection=selection_from_args(args, historical=False),
                    start=args.start, end=args.end, resume=args.resume,
                    lookback_days=args.lookback_days,
                )
        else:
            output = aggregate(args)
    except (ValueError, OSError, FIRMSAPIError) as exc:
        report = getattr(exc, "report", {"status": "failed", "error": str(exc)})
        write_report(getattr(args, "report", None), report)
        parser.exit(1, f"Processing failed: {exc}\n")
    except SQLAlchemyError:
        write_report(getattr(args, "report", None), {
            "status": "failed", "error": "Database operation failed; check connectivity and migrations",
        })
        parser.exit(1, "Database operation failed; check connectivity and apply migrations\n")
    write_report(getattr(args, "report", None), output.get("report", output))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
