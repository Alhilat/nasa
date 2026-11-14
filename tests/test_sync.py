"""Checkpoint orchestration with an injected importer and mock availability; no observations."""
from datetime import date
from types import SimpleNamespace

import pytest

from firescope_pipeline.selection import Selection
from firescope_pipeline import sync


class Factory:
    def __init__(self, next_date=None):
        self.next_date = next_date
    def __call__(self):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        pass
    def get(self, *_args):
        return SimpleNamespace(next_date=self.next_date) if self.next_date else None


class Client:
    requests = 0
    def __init__(self):
        self.days = []
    def availability(self, _source):
        return date(2025, 1, 1), date(2025, 12, 31)
    def area(self, _source, _bbox, day, days):
        self.days.append(day)
        return b"test transport payload; importer is injected"


def test_resume_replays_lookback_for_late_observations(monkeypatch):
    factory = Factory(date(2025, 1, 5))
    client, checkpoints = Client(), []
    def importer(_factory, _content, **kwargs):
        checkpoints.append(kwargs["checkpoint"])
        return {"job_id": "test-only"}
    monkeypatch.setattr(sync, "import_source", importer)
    result = sync.sync_api(factory, client, source="MODIS_NRT", selection=Selection(bbox=(0, 0, 1, 1)),
                           start=date(2025, 1, 1), end=date(2025, 1, 7), resume=True)
    assert client.days == [date(2025, 1, day) for day in (3, 4, 5, 6)]
    assert checkpoints[-1]["next_date"] == date(2025, 1, 7)
    assert result["next_date"] == "2025-01-07"
    assert "MAP_KEY" not in str(checkpoints)


def test_failed_import_stops_before_later_windows(monkeypatch):
    client = Client()
    def importer(*_args, **_kwargs):
        raise ValueError("Invalid source rows")
    monkeypatch.setattr(sync, "import_source", importer)
    with pytest.raises(ValueError, match="Invalid source rows"):
        sync.sync_api(Factory(), client, source="MODIS_NRT", selection=Selection(bbox=(0, 0, 1, 1)),
                      start=date(2025, 1, 1), end=date(2025, 1, 4))
    assert client.days == [date(2025, 1, 1)]


def test_outside_availability_does_not_download_or_mark_coverage():
    client = Client()
    with pytest.raises(ValueError, match="outside"):
        sync.sync_api(Factory(), client, source="MODIS_NRT", selection=Selection(bbox=(0, 0, 1, 1)),
                      start=date(2024, 1, 1), end=date(2025, 1, 4))
    assert not client.days
