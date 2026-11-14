"""Synthetic dashboard transport/selection tests; never application observations."""

import csv
import io
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.dashboard_routes import compare_aggregate, observation_csv, whole_days
from app.db import get_session
from app.main import app
from app.schemas import ObservationQuery
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

JOB = UUID("00000000-0000-0000-0000-000000000001")


def selection(**changes):
    return ObservationQuery(
        **{
            "bbox": [34, 29, 40, 34],
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-02-01T00:00:00Z",
            "sensors": ["MODIS_TERRA"],
            **changes,
        }
    )


def test_whole_utc_days_exclude_partial_edges_and_handle_leap_years():
    first, last = whole_days(
        datetime.fromisoformat("2024-02-28T01:00:00+02:00"),
        datetime.fromisoformat("2024-03-01T00:00:00+02:00"),
    )
    assert first == datetime(2024, 2, 28, tzinfo=UTC)
    assert last == datetime(2024, 2, 29, tzinfo=UTC)


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.statements = []

    def get(self, *_args):
        return SimpleNamespace(
            kind="aggregate",
            status="succeeded",
            algorithm_version="wgs84-grid-daily-v2",
            parameters={
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-02-01T00:00:00Z",
                "grid_size_deg": 1,
            },
            output_metadata={"fixture": "synthetic only"},
        )

    def execute(self, statement):
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return SimpleNamespace(all=lambda: next(self.responses))


def test_comparison_uses_whole_cells_and_source_lineage_without_pooling_sensors():
    stored = [
        SimpleNamespace(
            sensor_code="MODIS_TERRA", day=date(2024, 1, 1), cells=1, _mapping={"count": 2}
        )
    ]
    raw = [SimpleNamespace(sensor_code="MODIS_TERRA", day=date(2024, 1, 1), _mapping={"count": 2})]
    session = FakeSession([stored, raw])
    result = compare_aggregate(JOB, selection(), session)
    assert result["raw_count"] == result["grid_count"] == 2
    assert result["archive_counts_match"] is True
    assert "ST_Covers" in session.statements[0]
    assert "harmonized_aggregates.cell" in session.statements[0]
    assert "EXISTS" in session.statements[1]
    assert "aggregate_sources.job_id" in session.statements[1]
    assert "matched_bins.grid_x" in session.statements[1]
    assert "matched_bins.grid_y" in session.statements[1]
    assert "source" in result["scope"]


def test_empty_comparison_remains_unknown():
    result = compare_aggregate(JOB, selection(), FakeSession([[], []]))
    assert result["raw_count"] is None
    assert result["grid_count"] is None
    assert result["archive_counts_match"] is None


def test_changed_archive_counts_are_disclosed():
    stored = [
        SimpleNamespace(
            sensor_code="MODIS_TERRA", day=date(2024, 1, 1), cells=1, _mapping={"count": 2}
        )
    ]
    result = compare_aggregate(JOB, selection(), FakeSession([stored, []]))
    assert result["archive_counts_match"] is False


def test_csv_preserves_nulls_sources_and_exact_scope_and_escapes_formula_text():
    row = SimpleNamespace(
        _mapping={
            "id": 1,
            "sensor_code": "MODIS_TERRA",
            "acquired_at": datetime(2024, 1, 1, tzinfo=UTC),
            "longitude": -179.0,
            "latitude": 31,
            "frp_mw": None,
            "uncertainty": {"coverage_known": False},
            "source_id": JOB,
            "sha256": "a" * 64,
            "original_filename": '=HYPERLINK("bad")',
        }
    )
    session = FakeSession([[row]])
    result = observation_csv(selection(), session)
    rows = list(csv.DictReader(io.StringIO(result.body.decode())))
    assert len(rows) == 1
    assert rows[0]["frp_mw"] == ""
    assert rows[0]["original_filename"].startswith("'=")
    assert rows[0]["longitude"] == "-179.0"
    assert rows[0]["sha256"] == "a" * 64
    assert "bbox" in rows[0]["query_json"]
    assert "original_bytes" not in session.statements[0]


@pytest.mark.parametrize(
    "changes", [{"confidence": "high"}, {"bbox": None}, {"start": None}, {"sensors": ["UNKNOWN"]}]
)
def test_comparison_rejects_non_equivalent_selections(changes):
    app.dependency_overrides[get_session] = lambda: FakeSession([])
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/analytics/comparison/{JOB}",
                json=selection(**changes).model_dump(mode="json"),
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_empty_csv_is_a_real_header_only_download():
    app.dependency_overrides[get_session] = lambda: FakeSession([[]])
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/observations/export.csv", json=selection().model_dump(mode="json")
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/csv")
            assert len(response.text.splitlines()) == 1
    finally:
        app.dependency_overrides.clear()
