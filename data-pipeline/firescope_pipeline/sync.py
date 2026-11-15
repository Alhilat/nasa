import hashlib
import json
from datetime import UTC, datetime, timedelta

from app.models import ImportCheckpoint

from firescope_pipeline.firms_api import API_SOURCES, BASE_URL
from firescope_pipeline.selection import Selection
from firescope_pipeline.service import import_source


def sync_api(factory, client, *, source, selection, start, end, resume=False, lookback_days=2,
             window_days=1):
    if (source not in API_SOURCES or start >= end or not 0 <= lookback_days <= 30
            or not 1 <= window_days <= 5):
        raise ValueError("Provide a supported source, start < end, lookback 0–30, window 1–5")
    if selection.bbox is None or selection.bbox[0] >= selection.bbox[2]:
        raise ValueError("API synchronization requires a non-wrapping bbox")
    parameters = {"source": source, "bbox": list(selection.bbox), "polygon": selection.polygon,
                  "anchor_start": start.isoformat(), "policy": "firms-csv-v2"}
    stream_key = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    next_date = start
    if resume:
        with factory() as session:
            checkpoint = session.get(ImportCheckpoint, stream_key)
            if checkpoint:
                next_date = max(start, checkpoint.next_date - timedelta(days=lookback_days))
    if next_date >= end:
        return {"stream_key": stream_key, "status": "up_to_date", "imports": []}
    available_start, available_end = client.availability(source)
    if next_date < available_start or end - timedelta(days=1) > available_end:
        raise ValueError(
            f"Requested interval is outside {source} availability "
            f"{available_start.isoformat()} through {available_end.isoformat()}; "
            "use historical CSVs or adjust the interval"
        )
    results = []
    while next_date < end:
        days = min(window_days, (end - next_date).days)
        content = client.area(source, selection.bbox, next_date, days=days)
        following = next_date + timedelta(days=days)
        window = Selection(
            bbox=selection.bbox, polygon=selection.polygon,
            start=datetime.combine(next_date, datetime.min.time(), tzinfo=UTC),
            end=datetime.combine(following, datetime.min.time(), tzinfo=UTC),
        )
        result = import_source(
            factory, content, filename=f"{source}_{next_date.isoformat()}.csv",
            sensor=API_SOURCES[source], product_version="native",
            processing_level="nrt" if source.endswith("_NRT") else "standard",
            source_url=BASE_URL + "/api/area/", retrieved_at=datetime.now(UTC), selection=window,
            metadata={"transport": "FIRMS API", "request": {
                "source": source, "bbox": list(selection.bbox),
                "start_date": next_date.isoformat(), "day_range": days,
            }},
            checkpoint={"stream_key": stream_key, "next_date": following, "parameters": parameters},
        )
        results.append(result)
        next_date = following
    return {"stream_key": stream_key, "next_date": next_date.isoformat(),
            "requests": client.requests, "imports": results}
