import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Observation, ObservationRecord, RawRecord, SourceFile
from app.schemas import ObservationQuery


def observation_filters(query: ObservationQuery):
    conditions = []
    if query.bbox:
        west, south, east, north = query.bbox
        if west < east:
            envelope = func.ST_MakeEnvelope(west, south, east, north, 4326)
            conditions.append(func.ST_Covers(envelope, Observation.location))
        else:
            # Wrapped longitude range: two envelopes on either side of the antimeridian.
            conditions.append(or_(
                func.ST_Covers(func.ST_MakeEnvelope(west, south, 180, north, 4326),
                               Observation.location),
                func.ST_Covers(func.ST_MakeEnvelope(-180, south, east, north, 4326),
                               Observation.location),
            ))
    if query.polygon:
        polygon = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(query.polygon)), 4326)
        conditions.append(func.ST_Covers(polygon, Observation.location))
    if query.start:
        conditions.append(Observation.acquired_at >= query.start)
    if query.end:
        conditions.append(Observation.acquired_at < query.end)
    if query.sensors:
        conditions.append(Observation.sensor_code.in_(query.sensors))
    if query.confidence:
        conditions.append(Observation.confidence_class == query.confidence)
    return conditions


def query_observations(session: Session, query: ObservationQuery, max_results: int):
    limit = min(query.limit, max_results)
    statement = (
        select(Observation, SourceFile.sha256)
        .join(SourceFile, Observation.source_id == SourceFile.id)
        .where(*observation_filters(query))
        .order_by(Observation.acquired_at, Observation.id)
        .offset(query.offset).limit(limit + 1)
    )
    rows = session.execute(statement).all()
    features = []
    for observation, checksum in rows[:limit]:
        features.append({
            "type": "Feature",
            "id": observation.id,
            "geometry": {"type": "Point", "coordinates": [
                observation.longitude, observation.latitude,
            ]},
            "properties": {
                "id": observation.id,
                "sensor_code": observation.sensor_code,
                "acquired_at": observation.acquired_at.isoformat(),
                "frp_mw": observation.frp_mw,
                "confidence_native": observation.confidence_native,
                "confidence_class": observation.confidence_class,
                "source_id": str(observation.source_id),
                "source_sha256": checksum,
                "source_row": observation.source_row,
                "uncertainty": observation.uncertainty,
            },
        })
    return {
        "type": "FeatureCollection", "features": features,
        "metadata": {
            "returned": len(features), "offset": query.offset, "limit": limit,
            "has_more": len(rows) > limit, "crs": "EPSG:4326", "time_zone": "UTC",
        },
    }


def summarize(session: Session, query: ObservationQuery):
    conditions = observation_filters(query)
    total, first, last, sources, frp_known, frp_sum = session.execute(select(
        func.count(Observation.id), func.min(Observation.acquired_at),
        func.max(Observation.acquired_at), func.count(func.distinct(Observation.source_id)),
        func.count(Observation.frp_mw), func.sum(Observation.frp_mw),
    ).where(*conditions)).one()
    sensor_counts = session.execute(select(
        Observation.sensor_code, func.count(Observation.id),
    ).where(*conditions).group_by(Observation.sensor_code)).all()
    sources = session.scalar(select(func.count(func.distinct(RawRecord.source_id))).select_from(
        Observation,
    ).join(ObservationRecord, ObservationRecord.observation_id == Observation.id).join(
        RawRecord, RawRecord.id == ObservationRecord.raw_record_id,
    ).where(*conditions))
    day = func.date_trunc("day", func.timezone("UTC", Observation.acquired_at))
    daily = session.execute(select(
        day.label("day"), Observation.sensor_code, func.count(Observation.id).label("count"),
    ).where(*conditions).group_by(day, Observation.sensor_code).order_by(day)).all()
    return {
        "detection_count": total, "source_count": sources,
        "first_acquisition": first, "last_acquisition": last,
        "frp_known_count": frp_known, "frp_sum_mw": frp_sum,
        "by_sensor": dict(sensor_counts),
        "daily": [{"day": row.day.date().isoformat(), "sensor_code": row.sensor_code,
                   "count": row._mapping["count"]} for row in daily],
        "method": "exact-payload deduplicated observations; UTC daily bins; missing days omitted",
        "coverage_known": False,
    }
