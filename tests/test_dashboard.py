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


# All prototype inputs below are isolated synthetic software fixtures.
def prototype_record(identifier, sensor="MODIS_TERRA", **changes):
    return {
        "id": identifier,
        "sensor_code": sensor,
        "day": "2024-07-01",
        "year": 2024,
        "month": 7,
        "latitude": 31.951,
        "longitude": 35.931,
        "frp_mw": 10.0,
        "confidence_native": "80" if sensor.startswith("MODIS") else "n",
        "daynight": "D",
        "brightness_k": 330.0,
        "brightness_field": "brightness" if sensor.startswith("MODIS") else "bright_ti4",
        "source_id": str(JOB),
        "source_row": identifier,
        **changes,
    }


@pytest.mark.parametrize(
    "native,expected",
    [
        ("49", False),
        ("50", True),
        ("100", True),
        ("101", False),
        ("NaN", False),
        ("high", False),
        ("", False),
    ],
)
def test_prototype_modis_confidence_uses_native_numeric_scale(native, expected):
    from app.dashboard_routes import HarmonizationSelection, prototype_accepts

    assert (
        prototype_accepts(prototype_record(1, confidence_native=native), HarmonizationSelection())
        is expected
    )


@pytest.mark.parametrize(
    "native,expected",
    [
        ("n", True),
        ("h", True),
        ("Nominal", True),
        ("HIGH", True),
        ("l", False),
        ("low", False),
        ("50", False),
        (None, False),
    ],
)
def test_prototype_viirs_confidence_uses_native_categories(native, expected):
    from app.dashboard_routes import HarmonizationSelection, prototype_accepts

    record = prototype_record(1, "VIIRS_SNPP", confidence_native=native)
    assert prototype_accepts(record, HarmonizationSelection()) is expected
    assert (
        prototype_accepts(
            prototype_record(1, "VIIRS_SNPP", confidence_native="low"),
            HarmonizationSelection(viirs_confidence="all"),
        )
        is True
    )


def test_prototype_matches_javascript_rounding_in_both_hemispheres():
    from app.dashboard_routes import prototype_grid

    assert prototype_grid(1.125, -1.125) == (1.13, -1.12, "1.13_-1.12")
    assert prototype_grid(-0.001, 0.001) == (0.0, 0.0, "0.00_0.00")


def test_prototype_groups_sensor_detections_by_utc_day_and_cell_and_preserves_missingness():
    from app.dashboard_routes import HarmonizationSelection, analyze_harmonization

    records = [
        prototype_record(1),
        prototype_record(2, "VIIRS_SNPP", frp_mw=None, brightness_k=None, daynight="N"),
        prototype_record(3, "VIIRS_NOAA20", frp_mw=20, brightness_k=350),
        prototype_record(4, day="2024-07-02", frp_mw=None, brightness_k=None),
        prototype_record(5, confidence_native="49"),
    ]
    result = analyze_harmonization(HarmonizationSelection(), records, [])
    assert result["summary"] == {
        "input_detections": 5,
        "accepted_detections": 4,
        "rejected_detections": 1,
        "retention_percent": 80,
        "unified_cell_days": 2,
        "total_frp_mw": 30,
        "frp_known_count": 2,
    }
    cell = result["cells"][0]
    assert cell["raw_detections_count"] == 3
    assert cell["unified_fire_count"] == 1
    assert cell["total_frp_mw"] == 30 and cell["mean_frp_mw"] == 15
    assert cell["max_temp_k"] == 350 and cell["frp_known_count"] == 2
    assert cell["day_detections"] == 2 and cell["night_detections"] == 1
    assert cell["sensors_involved"] == ["MODIS_TERRA", "VIIRS_NOAA20", "VIIRS_SNPP"]
    assert cell["members"][1]["brightness_field"] == "bright_ti4"
    assert cell["members"][1]["source_row"] == 2
    assert result["cells"][1]["total_frp_mw"] is None
    assert result["cells"][1]["max_temp_k"] is None
    assert result["monthly"][0]["unified_cell_days"] is None
    assert result["monthly"][6]["unified_cell_days"] == 2
    assert result["coverage"] == "unknown" and result["operational_calibration"] is False


def test_prototype_overlap_uses_same_month_and_fixed_years_and_withholds_unsupported_agreement():
    from app.dashboard_routes import HarmonizationSelection, analyze_harmonization

    records = [
        prototype_record(1),
        prototype_record(2, "VIIRS_SNPP"),
        prototype_record(3, "VIIRS_SNPP", longitude=36.5),
        prototype_record(4, "VIIRS_SNPP", day="2025-07-01", year=2025),
        prototype_record(5, day="2024-08-01", month=8),
    ]
    result = analyze_harmonization(HarmonizationSelection(sensor_family="MODIS"), records, [])
    overlap = result["overlap"]
    assert overlap["modis_detections"] == 1 and overlap["viirs_detections"] == 2
    assert overlap["shared_cell_days"] == 1 and overlap["viirs_only_cell_days"] == 1
    assert overlap["jaccard"] == 0.5
    assert result["summary"]["input_detections"] == 1
    assert result["annual"][1]["raw_modis"] is None
    single = analyze_harmonization(HarmonizationSelection(), records[:1], [])
    assert single["overlap"]["jaccard"] is None


def test_prototype_reproducibility_and_display_caps_preserve_full_statistics():
    from app.dashboard_routes import HarmonizationSelection, analyze_harmonization

    records = [prototype_record(i, longitude=35 + i / 100) for i in range(1, 202)]
    records += [prototype_record(i, longitude=35.01) for i in range(202, 225)]
    sources = [{"id": "b", "sha256": "b" * 64}, {"id": "a", "sha256": "a" * 64}]
    result = analyze_harmonization(HarmonizationSelection(), records, sources)
    reordered = analyze_harmonization(
        HarmonizationSelection(), list(reversed(records)), list(reversed(sources))
    )
    assert result["analysis_id"] == reordered["analysis_id"]
    assert len(result["cells"]) == 200 and result["cells_total"] == 201
    assert result["cells_truncated"] is True
    assert result["summary"]["input_detections"] == 224
    assert result["cells"][0]["members_truncated"] is True
    assert len(result["cells"][0]["members"]) == 20
    assert result["cells"][0]["raw_detections_count"] == 24
    assert result["cells"][0]["total_frp_mw"] == 240
    changed = analyze_harmonization(
        HarmonizationSelection(modis_confidence_min=90), records, sources
    )
    assert changed["analysis_id"] != result["analysis_id"]


@pytest.mark.parametrize(
    "body",
    [
        {"month": 13},
        {"year": 1999},
        {"modis_confidence_min": -1},
        {"viirs_confidence": "bogus"},
        {"sensor_family": "unknown"},
        {"bbox": [34, 35, 40, 29]},
        {"extra": True},
    ],
)
def test_prototype_endpoint_validates_controls(body):
    app.dependency_overrides[get_session] = lambda: FakeSession([])
    try:
        with TestClient(app) as client:
            assert client.post("/api/v1/analytics/harmonization", json=body).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_prototype_endpoint_reads_raw_temperature_and_primary_source_metadata():
    record = SimpleNamespace(
        id=1,
        sensor_code="VIIRS_SNPP",
        acquired_at=datetime(2024, 7, 1, tzinfo=UTC),
        latitude=31.95,
        longitude=35.93,
        frp_mw=None,
        confidence_native="n",
        daynight="N",
        source_id=JOB,
        source_row=2,
        raw_properties={"bright_ti4": "331.5"},
    )
    source = SimpleNamespace(
        _mapping={"id": JOB, "original_filename": "synthetic-test.csv", "sha256": "a" * 64}
    )
    session = FakeSession([[record], [source]])
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/analytics/harmonization", json={})
        assert response.status_code == 200
        result = response.json()
        assert result["cells"][0]["max_temp_k"] == 331.5
        assert result["sources"][0]["id"] == str(JOB)
        assert "JOIN raw_records" in session.statements[0]
        assert "ST_Covers" in session.statements[0]
        assert all("original_bytes" not in statement for statement in session.statements)
    finally:
        app.dependency_overrides.clear()


def test_prototype_refuses_oversized_selection_before_returning_partial_statistics():
    from app.dashboard_routes import HarmonizationSelection, harmonization_engine
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        harmonization_engine(HarmonizationSelection(), FakeSession([[None] * 250001]))
    assert error.value.status_code == 413
