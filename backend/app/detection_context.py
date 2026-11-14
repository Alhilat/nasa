"""Descriptive archive context for a detection; this is not a fire classifier."""

from datetime import timedelta

from geoalchemy2 import Geography
from sqlalchemy import cast, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models import Observation

RADIUS_METERS = 2000
NEAR_HOURS = 24
HISTORY_DAYS = 365


def detection_context(session: Session, observation: Observation) -> dict:
    """Count other archive records by distance and time, independent of UI filters."""
    instant = observation.acquired_at
    near_start = instant - timedelta(hours=NEAR_HOURS)
    near_end = instant + timedelta(hours=NEAR_HOURS)
    history_start = instant - timedelta(days=HISTORY_DAYS)
    history_end = instant + timedelta(days=HISTORY_DAYS)
    near = (Observation.acquired_at >= near_start) & (Observation.acquired_at <= near_end)
    other_times = or_(Observation.acquired_at < near_start, Observation.acquired_at > near_end)
    utc_day = func.date_trunc("day", func.timezone("UTC", Observation.acquired_at))
    utc_month = func.date_trunc("month", func.timezone("UTC", Observation.acquired_at))
    point = func.ST_SetSRID(func.ST_MakePoint(observation.longitude, observation.latitude), 4326)
    row = session.execute(select(
        func.count(Observation.id).filter(near),
        func.count(distinct(utc_day)).filter(near),
        func.count(Observation.id).filter(other_times),
        func.count(distinct(utc_month)).filter(other_times),
    ).where(
        Observation.id != observation.id,
        Observation.acquired_at >= history_start,
        Observation.acquired_at <= history_end,
        func.ST_DWithin(
            cast(Observation.location, Geography), cast(point, Geography), RADIUS_METERS,
        ),
    )).one()
    return {
        "observation_id": observation.id,
        "radius_meters": RADIUS_METERS,
        "nearby": {"start": near_start, "end": near_end, "detections": row[0], "utc_days": row[1]},
        "history": {"start": history_start, "end": history_end,
                    "detections": row[2], "utc_months": row[3]},
        "scope": "All archived sensors and confidence classes; selected detection excluded.",
        "coverage": "Archive coverage is unknown. No detections do not establish absence of fire.",
        "interpretation": "Satellite detections cannot distinguish fire from other heat sources.",
        "unavailable": ["Land cover", "Industrial facilities", "Independent fire reports",
                        "Confirming imagery"],
    }
