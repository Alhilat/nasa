"""Synthetic software fixtures; these counts are never represented as NASA observations."""

import csv
import io
import json

import pytest
from app.db import get_session
from app.history import HistoryQuery, analyze, calendar_csv
from app.history_export import main as export_main
from app.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError

SENSOR = "MODIS_TERRA"
SOURCES = [
    {
        "id": "source-a",
        "sha256": "a" * 64,
        "source_url": "https://example.org/synthetic-only.csv",
        "original_filename": 'synthetic,"fixture".csv',
        "product_version": "test",
        "processing_level": "test",
        "retrieved_at": "2026-01-01T00:00:00+00:00",
    }
]


def query(**changes):
    return HistoryQuery(
        **{
            "start_year": 2013,
            "end_year": 2016,
            "bbox": [34, 29, 40, 34],
            "sensors": [SENSOR],
            "min_baseline_years": 3,
            "complete_months": [
                {"sensor_code": SENSOR, "month": f"{y}-01", "reference": "test audit"}
                for y in range(2013, 2017)
            ],
            **changes,
        }
    )


def records(counts):
    rows = []
    for month, count in counts.items():
        for _ in range(count):
            rows.append(
                {
                    "id": len(rows) + 1,
                    "sensor_code": SENSOR,
                    "acquired_at": month + "-01T00:00:00+00:00",
                    "latitude": 31,
                    "longitude": 35,
                    "source_ids": ["source-a"],
                    "record_hash": str(len(rows)),
                    "confidence_class": "high",
                }
            )
    return rows


def month(result, label):
    return next(r for r in result["monthly"] if r["month"] == label)


def test_missing_months_are_null_but_attested_empty_month_is_zero():
    result = analyze(query(), [], [])
    assert month(result, "2013-01")["count"] == 0
    assert month(result, "2013-02")["count"] is None
    assert result["yearly"][0]["count"] is None
    assert result["concentration"][0]["herfindahl_index"] is None


def test_equivalent_months_prior_years_and_percentile_flags():
    rows = records({"2013-01": 10, "2014-01": 20, "2015-01": 30, "2016-01": 100, "2013-02": 500})
    result = analyze(query(), rows, SOURCES)
    january = month(result, "2016-01")
    assert january["historical_median"] == 20
    assert january["baseline_years"] == [2013, 2014, 2015]
    assert january["lower_threshold"] == 11
    assert january["upper_threshold"] == 29
    assert january["anomaly_status"] == "unusually_high"
    assert january["robust_z"] == pytest.approx(80 / 14.826)
    assert month(result, "2013-01")["historical_median"] is None
    assert month(result, "2013-02")["anomaly_status"] == "incomplete_period"


@pytest.mark.parametrize(
    ("value", "status"), [(0, "unusually_low"), (29, "within_range"), (30, "unusually_high")]
)
def test_thresholds_are_strict(value, status):
    result = analyze(
        query(), records({"2013-01": 10, "2014-01": 20, "2015-01": 30, "2016-01": value}), SOURCES
    )
    assert month(result, "2016-01")["anomaly_status"] == status


def test_zero_mad_and_zero_previous_count_are_explicit():
    result = analyze(query(), records({"2016-01": 1}), SOURCES)
    row = month(result, "2016-01")
    assert row["robust_z"] is None
    assert row["anomaly_status"] == "unusually_high"
    assert row["year_over_year"]["percent_change"] is None
    assert row["year_over_year"]["percent_change_reason"] == "zero_previous_count"


def test_incomplete_positive_counts_are_excluded_from_baseline_and_comparisons():
    result = analyze(
        query(complete_months=[]),
        records({"2013-01": 10, "2014-01": 20, "2015-01": 30, "2016-01": 999}),
        SOURCES,
    )
    row = month(result, "2016-01")
    assert row["count"] == 999
    assert row["baseline_size"] == 0
    assert row["historical_median"] is None
    assert row["year_over_year"]["difference"] is None
    assert row["anomaly_status"] == "incomplete_period"
    assert result["seasonal_profiles"][0]["median"] is None


def test_yearly_comparisons_use_same_complete_months_not_unequal_annual_totals():
    declarations = [
        {"sensor_code": SENSOR, "month": m, "reference": "test"}
        for m in ["2015-01", "2015-02", "2016-01"]
    ]
    result = analyze(
        query(complete_months=declarations),
        records({"2015-01": 10, "2015-02": 1000, "2016-01": 20}),
        SOURCES,
    )
    comparison = result["yearly"][-1]["year_over_year"]
    assert comparison["matched_months"] == [1]
    assert comparison["current_count"] == 20
    assert comparison["previous_count"] == 10
    assert comparison["percent_change"] == 100
    assert result["yearly"][-1]["count"] is None


def test_complete_year_calendar_can_represent_attested_zero_archive_counts():
    declarations = [
        {"sensor_code": SENSOR, "month": f"2016-{m:02d}", "reference": "test"} for m in range(1, 13)
    ]
    result = analyze(query(complete_months=declarations), [], [])
    assert result["yearly"][-1]["count"] == 0
    assert len(result["yearly"][-1]["complete_months"]) == 12


def test_spatial_sensor_and_confidence_selection_are_shared_across_years():
    rows = records({"2013-01": 2, "2014-01": 3})
    rows[0]["longitude"] = 0  # outside selected area
    rows[1]["sensor_code"] = "VIIRS_SNPP"
    rows[2]["confidence_class"] = "low"
    result = analyze(query(confidence="high"), rows, SOURCES)
    assert month(result, "2013-01")["count"] == 0
    assert month(result, "2014-01")["count"] == 2
    assert result["concentration"][0]["observed_count"] == 2
    assert result["spatial"]["features"][0]["properties"]["count"] == 2


def test_polygon_and_bbox_intersect_and_include_boundaries():
    polygon = {
        "type": "Polygon",
        "coordinates": [[[35, 31], [36, 31], [36, 32], [35, 32], [35, 31]]],
    }
    rows = records({"2013-01": 2})
    rows[1]["longitude"] = 37
    result = analyze(query(polygon=polygon), rows, SOURCES)
    assert month(result, "2013-01")["count"] == 1


def test_sensors_are_never_pooled_and_spatial_shares_sum_to_one():
    rows = records({"2013-01": 4})
    rows[0]["sensor_code"] = "VIIRS_SNPP"
    rows[1]["longitude"] = 37
    result = analyze(query(sensors=[SENSOR, "VIIRS_SNPP"]), rows, SOURCES)
    for sensor in [SENSOR, "VIIRS_SNPP"]:
        features = [
            f for f in result["spatial"]["features"] if f["properties"]["sensor_code"] == sensor
        ]
        assert sum(f["properties"]["share"] for f in features) == pytest.approx(1)
    assert result["concentration"][0]["herfindahl_index"] == pytest.approx(5 / 9)


def test_antimeridian_poles_and_utc_month_boundaries():
    rows = records({"2013-01": 3})
    rows[0].update(longitude=180, latitude=90)
    rows[1].update(longitude=-179, latitude=89)
    rows[2].update(longitude=0, latitude=0)
    rows[0]["acquired_at"] = "2013-02-01T01:00:00+02:00"
    result = analyze(query(bbox=[170, -90, -170, 90]), rows, SOURCES)
    assert month(result, "2013-01")["count"] == 2
    for feature in result["spatial"]["features"]:
        assert all(
            -180 <= x <= 180 and -90 <= y <= 90 for x, y in feature["geometry"]["coordinates"][0]
        )


def test_reproducible_hash_csv_and_offline_replay(tmp_path):
    rows = records({"2013-01": 3})
    source_b = {**SOURCES[0], "id": "source-b", "sha256": "b" * 64}
    rows[0]["source_ids"].append("source-b")
    sources = [*SOURCES, source_b]
    result = analyze(query(), rows, sources)
    assert result == analyze(query(), list(reversed(rows)), list(reversed(sources)))
    assert result["analysis_id"] != analyze(query(percentile=90), rows, sources)["analysis_id"]
    csv_rows = list(csv.DictReader(io.StringIO(calendar_csv(result))))
    assert len(csv_rows) == 48
    assert csv_rows[1]["count"] == ""
    assert len(json.loads(csv_rows[0]["source_metadata_json"])) == 2
    assert csv_rows[0]["analysis_id"] == result["analysis_id"]
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"query": query().model_dump(mode="json"), "records": rows, "sources": sources}),
        encoding="utf-8",
    )
    for name in ["one", "two"]:
        export_main(["--replay", str(snapshot), "--output", str(tmp_path / name)])
    for filename in ["analysis.json", "calendar.csv", "input-snapshot.json"]:
        assert (tmp_path / "one" / filename).read_bytes() == (
            tmp_path / "two" / filename
        ).read_bytes()


@pytest.mark.parametrize(
    "changes",
    [
        {"bbox": None},
        {"start_year": 2017},
        {"end_year": 2099},
        {"percentile": 100},
        {"percentile": float("nan")},
        {"min_baseline_years": 2},
        {"sensors": ["UNKNOWN"]},
        {"grid_size_deg": 0.3},
        {"baseline_start_year": 2012},
        {"baseline_end_year": 2017},
        {"offset": 1},
        {"start": "2013-01-01T00:00:00Z"},
        {"complete_months": [{"sensor_code": SENSOR, "month": "2013-13", "reference": "test"}]},
        {"complete_months": [{"sensor_code": SENSOR, "month": "2013-01", "reference": " "}]},
        {"complete_months": [{"sensor_code": SENSOR, "month": "2012-01", "reference": "test"}]},
        {"complete_months": [{"sensor_code": SENSOR, "month": "2013-01", "reference": "test"}] * 2},
    ],
)
def test_invalid_selections_are_rejected(changes):
    with pytest.raises(ValidationError):
        query(**changes)


def test_endpoint_json_csv_validation_and_cors(monkeypatch):
    monkeypatch.setattr(
        "app.history_routes.load_inputs",
        lambda *_: (
            records({"2013-01": 2}),
            SOURCES,
        ),
    )
    app.dependency_overrides[get_session] = lambda: object()
    try:
        with TestClient(app) as client:
            payload = query().model_dump(mode="json")
            response = client.post("/api/v1/analytics/history", json=payload)
            assert response.status_code == 200
            assert response.json()["forecasting"] is False
            export = client.post(
                "/api/v1/analytics/history/export.csv",
                json=payload,
                headers={"Origin": "http://localhost:5173"},
            )
            assert export.status_code == 200
            assert export.headers["X-Analysis-ID"] == response.json()["analysis_id"]
            assert "x-analysis-id" in export.headers["access-control-expose-headers"].lower()
            assert export.text == calendar_csv(response.json())
            assert (
                client.post("/api/v1/analytics/history", json={**payload, "bbox": None}).status_code
                == 422
            )
    finally:
        app.dependency_overrides.clear()


def test_repository_refuses_truncated_analytics(monkeypatch):
    from app.history_routes import load_inputs

    class FakeResult:
        def all(self):
            return [object(), object()]

    class FakeSession:
        def execute(self, _statement):
            return FakeResult()

    from fastapi import HTTPException

    monkeypatch.setattr("app.history_routes.MAX_RECORDS", 1)
    with pytest.raises(HTTPException) as exc:
        load_inputs(FakeSession(), query())
    assert exc.value.status_code == 413


def test_repository_retains_all_source_copies_without_multiplying_counts():
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import UUID

    from app.history_routes import load_history

    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")
    observation = SimpleNamespace(
        id=1,
        sensor_code=SENSOR,
        acquired_at=datetime(2013, 1, 1, tzinfo=UTC),
        latitude=31,
        longitude=35,
        record_hash="synthetic-hash",
        source_id=first,
        confidence_class="high",
    )
    sources = [
        SimpleNamespace(
            _mapping={
                "id": source_id,
                "sha256": str(source_id),
                "retrieved_at": datetime(2014, 1, 1, tzinfo=UTC),
                "source_metadata": {"fixture": "synthetic"},
            }
        )
        for source_id in [first, second]
    ]

    class FakeSession:
        def __init__(self):
            self.responses = iter([[observation], [(1, first), (1, second)], sources])
            self.statements = []

        def execute(self, statement):
            self.statements.append(str(statement))
            return SimpleNamespace(all=lambda: next(self.responses))

    session = FakeSession()
    result = load_history(session, query())
    row = month(result, "2013-01")
    assert row["count"] == 1
    assert row["source_ids"] == [str(first), str(second)]
    assert len(result["sources"]) == 2
    assert result["sources"][0]["source_metadata"] == {"fixture": "synthetic"}
    assert all("original_bytes" not in statement for statement in session.statements)
    assert "ST_Covers" in session.statements[0]
    assert "acquired_at >=" in session.statements[0]
    assert "acquired_at <" in session.statements[0]
