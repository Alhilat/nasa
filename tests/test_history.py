"""Synthetic software fixtures; these counts are never represented as NASA observations."""

import csv
import io
import json

import pytest
from app.completeness import JORDAN_COUNTRY_GEOJSON
from app.db import get_session
from app.history import HISTORY_METRIC, HistoryQuery, analyze, calendar_csv
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


def _annual_country_source(year: int, product: str = "modis", country: str = "Jordan", **extra):
    sensor_family = "MODIS" if product == "modis" else "VIIRS_SNPP"
    return {
        "id": f"{product}-{year}-{country}",
        "sha256": f"{year:04d}" + ("c" * 60),
        "original_filename": f"{product}_{year}_{country}.csv",
        "source_url": (
            f"https://firms.modaps.eosdis.nasa.gov/data/country/"
            f"{product}/{year}/{product}_{year}_{country}.csv"
        ),
        "sensor_code": sensor_family,
        "product_version": "6.2" if product == "modis" else "2",
        "processing_level": "standard",
        "quality_report": {
            "status": "imported",
            "invalid_rows": 0,
            "filters": {},
            "source_sha256": f"{year:04d}" + ("c" * 60),
        },
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "source_metadata": {},
        **extra,
    }


def _api_window_source(
    source_id: str,
    sensor_code: str,
    start_date: str,
    day_range: int = 5,
    processing_level: str = "standard",
    bbox: list[float] | None = None,
):
    req_bbox = bbox or [34.8, 29.0, 39.4, 33.5]
    return {
        "id": source_id,
        "sha256": (source_id.encode().hex() + "0" * 64)[:64],
        "original_filename": f"{source_id}.csv",
        "source_url": f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/REDACTED/{source_id}",
        "sensor_code": sensor_code,
        "product_version": "6.1" if processing_level == "standard" else "6.1NRT",
        "quality_report": {
            "status": "imported",
            "invalid_rows": 0,
            "filters": {},
            "source_sha256": (source_id.encode().hex() + "0" * 64)[:64],
        },
        "processing_level": processing_level,
        "retrieved_at": "2026-11-14T00:00:00+00:00",
        "source_metadata": {
            "request": {
                "source": "MODIS_SP" if processing_level == "standard" else "MODIS_NRT",
                "bbox": req_bbox,
                "start_date": start_date,
                "day_range": day_range,
            }
        },
    }


def test_source_audited_completeness_distinguishes_observation_coverage_and_preserves_unknowns():
    sources = [_annual_country_source(y) for y in range(2013, 2017)]
    # Add an invalid-row source for 2017 to verify rejected/dirty sources never attest completeness.
    sources.append(
        _annual_country_source(2017, quality_report={"status": "rejected", "invalid_rows": 2})
    )
    rows = []
    for idx, (yr, cnt) in enumerate([(2013, 5), (2014, 10), (2015, 15), (2016, 40)], start=1):
        for n in range(cnt):
            rows.append(
                {
                    "id": idx * 100 + n,
                    "sensor_code": SENSOR,
                    "acquired_at": f"{yr}-01-10T00:00:00+00:00",
                    "latitude": 31.5,
                    "longitude": 35.8,
                    "source_ids": [f"modis-{yr}-Jordan"],
                    "record_hash": f"{yr}-{n}",
                    "confidence_class": "high",
                }
            )
    q = query(
        start_year=2013,
        end_year=2017,
        complete_months=[],
        bbox=None,
        polygon=JORDAN_COUNTRY_GEOJSON,
    )
    result = analyze(q, rows, sources)
    assert result["observation_coverage"] == "unknown"
    assert result["completeness_summary"]["observation_coverage"] == "unknown"

    # 2016-01 is audited complete with 3 prior reference years (2013..2015) and unusually_high.
    jan_2016 = month(result, "2016-01")
    assert jan_2016["completeness"] == "complete"
    assert jan_2016["archive_completeness"] == "complete"
    assert jan_2016["completeness_origin"] == "source_audit"
    assert jan_2016["observation_coverage"] == "unknown"
    assert jan_2016["missing_data_status"] == "complete_assessed"
    assert jan_2016["baseline_period"] == "2013–2015"
    assert jan_2016["baseline_size"] == 3
    assert jan_2016["historical_median"] == 10
    assert jan_2016["anomaly_status"] == "unusually_high"

    # 2016-02 had 0 detections in a validated annual country file -> count is 0, not None.
    feb_2016 = month(result, "2016-02")
    assert feb_2016["completeness"] == "complete"
    assert feb_2016["count"] == 0
    assert feb_2016["historical_median"] == 0
    assert feb_2016["observation_coverage"] == "unknown"

    # 2017-01 had only a rejected source -> preserved as unknown (count is None, not 0).
    jan_2017 = month(result, "2017-01")
    assert jan_2017["completeness"] == "unknown"
    assert jan_2017["archive_completeness"] == "unknown"
    assert jan_2017["missing_data_status"] == "unattested_or_missing_source"
    assert jan_2017["count"] is None
    assert jan_2017["anomaly_status"] == "incomplete_period"


def test_incomplete_months_partial_api_nrt_and_spatial_scope_mismatch():
    from app.completeness import NAMED_AREAS

    # Annual country files for 2022..2025 + API windows in 2026:
    # - 2026-01: full 31 days of standard API windows
    # - 2026-02: mixed standard + NRT API windows
    # - 2026-03: full 31 days of NRT API windows
    # - 2026-04: partial month (only 10 of 30 days)
    sources = [_annual_country_source(y) for y in range(2022, 2026)]
    for day_offset in range(0, 31, 5):
        d = f"2026-01-{1 + day_offset:02d}"
        sources.append(_api_window_source(f"api-jan-{d}", "MODIS", d, day_range=5))
    for day_offset in range(0, 25, 5):
        d = f"2026-02-{1 + day_offset:02d}"
        sources.append(_api_window_source(f"api-feb-sp-{d}", "MODIS", d, day_range=5))
    sources.append(
        _api_window_source(
            "api-feb-nrt", "MODIS", "2026-02-25", day_range=5, processing_level="nrt"
        )
    )
    for day_offset in range(0, 31, 5):
        d = f"2026-03-{1 + day_offset:02d}"
        sources.append(
            _api_window_source(f"api-mar-nrt-{d}", "MODIS", d, day_range=5, processing_level="nrt")
        )
    sources.append(_api_window_source("api-apr-partial", "MODIS", "2026-04-01", day_range=10))

    # 1. Unclipped study envelope [34, 29, 40, 34]: 2026-01 is flagged as spatial_scope_mismatch
    # because 2022..2025 use Jordan country files while 2026 API uses the wider bbox.
    envelope_q = query(
        start_year=2022,
        end_year=2026,
        complete_months=[],
        bbox=[34.8, 29, 39.4, 33.5],
        min_baseline_years=3,
    )
    envelope_res = analyze(envelope_q, [], sources)
    assert month(envelope_res, "2026-01")["completeness"] == "complete"
    assert month(envelope_res, "2026-01")["archive_completeness"] == "complete"
    assert month(envelope_res, "2026-01")["missing_data_status"] == "complete_insufficient_baseline"
    assert month(envelope_res, "2025-01")["missing_data_status"] == "spatial_scope_mismatch"
    assert month(envelope_res, "2025-01")["count"] is None
    assert month(envelope_res, "2026-02")["missing_data_status"] == "mixed_processing_revisions"
    assert month(envelope_res, "2026-03")["archive_completeness"] == "nrt_complete"
    assert month(envelope_res, "2026-03")["missing_data_status"] == "nrt_unreconciled"
    assert month(envelope_res, "2026-04")["archive_completeness"] == "partial"
    assert month(envelope_res, "2026-04")["missing_data_status"] == "partial_month_archive"
    assert month(envelope_res, "2026-04")["count"] is None

    # 2. Jordan polygon selection: 2026-01 standard API windows are clipped to Jordan.
    poly_q = query(
        start_year=2022,
        end_year=2026,
        bbox=None,
        polygon=NAMED_AREAS["JOR_northwest"]["polygon"],
        complete_months=[],
        min_baseline_years=3,
    )
    poly_res = analyze(poly_q, [], sources)
    assert month(poly_res, "2026-01")["completeness"] == "complete"
    assert month(poly_res, "2026-01")["missing_data_status"] == "complete_assessed"
    assert month(poly_res, "2026-01")["baseline_years"] == [2022, 2023, 2024, 2025]
    assert month(poly_res, "2026-01")["count"] == 0
    # NRT and partial months remain incomplete even inside the Jordan polygon.
    assert month(poly_res, "2026-03")["completeness"] == "unknown"
    assert month(poly_res, "2026-03")["missing_data_status"] == "nrt_unreconciled"
    assert month(poly_res, "2026-04")["completeness"] == "unknown"
    assert month(poly_res, "2026-04")["missing_data_status"] == "partial_month_archive"


def test_insufficient_baseline_data_reports_status_and_withholds_anomaly():
    # Only 2013, 2014, and 2016 are complete; min_baseline_years is 4.
    declarations = [
        {"sensor_code": SENSOR, "month": f"{y}-05", "reference": "test"} for y in (2013, 2014, 2016)
    ]
    q = query(
        start_year=2013,
        end_year=2016,
        min_baseline_years=4,
        complete_months=declarations,
    )
    result = analyze(q, records({"2013-05": 4, "2014-05": 6, "2016-05": 50}), SOURCES)

    may_2013 = month(result, "2013-05")
    assert may_2013["completeness"] == "complete"
    assert may_2013["baseline_size"] == 0
    assert may_2013["baseline_period"] is None
    assert may_2013["anomaly_status"] == "insufficient_history"
    assert may_2013["missing_data_status"] == "complete_insufficient_baseline"
    assert "0 prior years" in may_2013["missing_data_reason"]

    may_2016 = month(result, "2016-05")
    assert may_2016["completeness"] == "complete"
    assert may_2016["baseline_years"] == [2013, 2014]
    assert may_2016["baseline_size"] == 2
    assert may_2016["baseline_period"] == "2013–2014"
    assert may_2016["min_baseline_years"] == 4
    assert may_2016["historical_median"] is None
    assert may_2016["anomaly_status"] == "insufficient_history"
    assert may_2016["missing_data_status"] == "complete_insufficient_baseline"
    assert "only 2 of 4 required" in may_2016["missing_data_reason"]


def test_sensor_operational_transitions_pre_operational_and_partial_start_months():
    sources = [
        _annual_country_source(2000, "modis"),
        _annual_country_source(2002, "modis"),
        _annual_country_source(2011, "modis"),
        _annual_country_source(2012, "modis"),
        _annual_country_source(2012, "viirs-snpp"),
    ]
    q = query(
        start_year=2000,
        end_year=2012,
        bbox=None,
        polygon=JORDAN_COUNTRY_GEOJSON,
        sensors=["MODIS_TERRA", "MODIS_AQUA", "VIIRS_SNPP"],
        complete_months=[],
    )
    result = analyze(q, [], sources)
    by_sensor_month = {(r["sensor_code"], r["month"]): r for r in result["monthly"]}

    # MODIS_TERRA: pre-operational 2000-01..2000-10, complete starting 2000-11.
    assert by_sensor_month["MODIS_TERRA", "2000-10"]["completeness"] == "unknown"
    assert (
        by_sensor_month["MODIS_TERRA", "2000-10"]["missing_data_status"] == "pre_operational_sensor"
    )
    assert by_sensor_month["MODIS_TERRA", "2000-10"]["count"] is None
    assert by_sensor_month["MODIS_TERRA", "2000-11"]["completeness"] == "complete"
    assert by_sensor_month["MODIS_TERRA", "2000-11"]["count"] == 0

    # MODIS_AQUA: pre-operational through 2002-06, partial start month 2002-07, complete 2002-08.
    assert (
        by_sensor_month["MODIS_AQUA", "2002-06"]["missing_data_status"] == "pre_operational_sensor"
    )
    assert by_sensor_month["MODIS_AQUA", "2002-07"]["completeness"] == "unknown"
    assert by_sensor_month["MODIS_AQUA", "2002-07"]["archive_completeness"] == "partial"
    assert (
        by_sensor_month["MODIS_AQUA", "2002-07"]["missing_data_status"]
        == "sensor_transition_partial_month"
    )
    assert by_sensor_month["MODIS_AQUA", "2002-07"]["count"] is None
    assert by_sensor_month["MODIS_AQUA", "2002-08"]["completeness"] == "complete"
    assert by_sensor_month["MODIS_AQUA", "2002-08"]["count"] == 0

    # VIIRS_SNPP: pre-operational through 2011-12, partial start 2012-01, complete 2012-02.
    assert (
        by_sensor_month["VIIRS_SNPP", "2011-12"]["missing_data_status"] == "pre_operational_sensor"
    )
    assert (
        by_sensor_month["VIIRS_SNPP", "2012-01"]["missing_data_status"]
        == "sensor_transition_partial_month"
    )
    assert by_sensor_month["VIIRS_SNPP", "2012-01"]["completeness"] == "unknown"
    assert by_sensor_month["VIIRS_SNPP", "2012-02"]["completeness"] == "complete"
    assert by_sensor_month["VIIRS_SNPP", "2012-02"]["count"] == 0

    transition_types = {
        (t["sensor_code"], t["transition_type"]) for t in result["sensor_transitions"]
    }
    assert ("MODIS_TERRA", "sensor_operational_start") in transition_types
    assert ("MODIS_AQUA", "sensor_operational_start") in transition_types
    assert ("VIIRS_SNPP", "sensor_operational_start") in transition_types


def test_validated_harmonized_series_used_when_supported_and_candidates_rejected():
    import hashlib

    sources = [
        _annual_country_source(2010, "modis"),
        _annual_country_source(2011, "modis"),
        _annual_country_source(2012, "modis"),
        _annual_country_source(2012, "viirs-snpp"),
        _annual_country_source(2013, "modis"),
        _annual_country_source(2013, "viirs-snpp"),
    ]
    # Observations in February:
    # MODIS_AQUA: 2010-02=10, 2011-02=12, 2012-02=11
    # VIIRS_SNPP: 2012-02=20, 2013-02=100
    obs = []
    spec = [
        ("MODIS_AQUA", 2010, 10, "modis-2010-Jordan"),
        ("MODIS_AQUA", 2011, 12, "modis-2011-Jordan"),
        ("MODIS_AQUA", 2012, 11, "modis-2012-Jordan"),
        ("VIIRS_SNPP", 2012, 20, "viirs-snpp-2012-Jordan"),
        ("VIIRS_SNPP", 2013, 100, "viirs-snpp-2013-Jordan"),
    ]
    for sensor_code, yr, cnt, src_id in spec:
        for i in range(cnt):
            obs.append(
                {
                    "id": len(obs) + 1,
                    "sensor_code": sensor_code,
                    "acquired_at": f"{yr}-02-15T10:00:00+00:00",
                    "latitude": 31.5,
                    "longitude": 35.8,
                    "source_ids": [src_id],
                    "record_hash": f"{sensor_code}-{yr}-{i}",
                    "confidence_class": "high",
                }
            )

    core_artifact = {
        "algorithm_version": "sensor-calibration-v1",
        "method": "quantile_mapping",
        "metric": HISTORY_METRIC,
        "training_pairs": 24,
        "training_hash": "0" * 64,
        "training_years": [2012, 2013],
        "training_regions": ["JOR_northwest"],
        "source_range": [0.0, 60.0],
        "parameters": {
            # Linear 0.5 scaling from VIIRS_SNPP to MODIS_AQUA reference scale
            "global": {"x": [0.0, 20.0, 120.0], "y": [0.0, 10.0, 60.0], "n": 24},
            "seasons": {
                "1": {"x": [0.0, 20.0, 120.0], "y": [0.0, 10.0, 60.0], "n": 12},
                "2": {"fallback": "global", "n": 4},
                "3": {"fallback": "global", "n": 4},
                "4": {"fallback": "global", "n": 4},
            },
            "tail_policy": "clip_and_flag",
            "quantile_method": "linear",
            "tie_policy": "mean_target_of_tied_source_quantiles",
        },
        "context": {
            "source": "VIIRS_SNPP",
            "reference": "MODIS_AQUA",
            "daynight": "all",
            "history_scope": {
                "bbox": None,
                "polygon": JORDAN_COUNTRY_GEOJSON,
                "confidence": None,
                "start_year": 2010,
                "end_year": 2013,
            },
            "native_product_versions": {"MODIS_AQUA": ["6.2"], "VIIRS_SNPP": ["2"]},
        },
        "bounded_occupancy": False,
    }
    model_version = hashlib.sha256(
        json.dumps(core_artifact, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    artifact = {**core_artifact, "model_version": model_version}

    q = query(
        start_year=2010,
        end_year=2013,
        bbox=None,
        polygon=JORDAN_COUNTRY_GEOJSON,
        sensors=["MODIS_AQUA", "VIIRS_SNPP"],
        min_baseline_years=3,
        complete_months=[],
    )

    # 1. Candidate-only model is NOT applied; VIIRS_SNPP in 2013-02 has 1 prior VIIRS year.
    candidate_res = analyze(
        q,
        obs,
        sources,
        calibration_models=[
            {
                "model_version": model_version,
                "method": "quantile_mapping",
                "status": "candidate_only",
                "artifact": artifact,
                "validation": {"status": "evaluated", "rejection_reasons": ["seasonal_mae_worse"]},
            }
        ],
    )
    assert candidate_res["harmonization"]["applied"] is False
    viirs_2013_cand = next(
        r
        for r in candidate_res["monthly"]
        if r["sensor_code"] == "VIIRS_SNPP" and r["month"] == "2013-02"
    )
    assert viirs_2013_cand["comparison_series"] == "native_sensor"
    assert viirs_2013_cand["harmonized_value"] is None
    assert viirs_2013_cand["baseline_years"] == [2012]
    assert viirs_2013_cand["baseline_size"] == 1
    assert viirs_2013_cand["anomaly_status"] == "insufficient_history"

    # 2. Supported-for-scope validated model IS applied across MODIS_AQUA -> VIIRS_SNPP.
    supported_res = analyze(
        q,
        obs,
        sources,
        calibration_models=[
            {
                "model_version": model_version,
                "method": "quantile_mapping",
                "status": "supported_for_scope",
                "artifact": artifact,
                "validation": {"status": "evaluated", "rejection_reasons": []},
            }
        ],
    )
    assert supported_res["harmonization"]["applied"] is True
    assert supported_res["harmonization"]["model_version"] == model_version
    viirs_2013 = next(
        r
        for r in supported_res["monthly"]
        if r["sensor_code"] == "VIIRS_SNPP" and r["month"] == "2013-02"
    )
    assert viirs_2013["count"] == 100  # Raw native count is preserved
    assert viirs_2013["comparison_series"] == "validated_harmonized"
    assert viirs_2013["harmonized_value"] == pytest.approx(50.0)
    assert viirs_2013["comparison_value"] == pytest.approx(50.0)
    assert viirs_2013["baseline_years"] == [2010, 2011, 2012]
    assert viirs_2013["baseline_sensors"] == ["MODIS_AQUA", "VIIRS_SNPP"]
    assert viirs_2013["historical_median"] == pytest.approx(10.0)
    assert viirs_2013["anomaly_status"] == "unusually_high"

    csv_rows = list(csv.DictReader(io.StringIO(calendar_csv(supported_res))))
    exported_2013 = next(
        r for r in csv_rows if r["sensor_code"] == "VIIRS_SNPP" and r["month"] == "2013-02"
    )
    assert exported_2013["comparison_series"] == "validated_harmonized"
    assert float(exported_2013["harmonized_value"]) == pytest.approx(50.0)
    assert exported_2013["baseline_period"] == "2010–2012"
    assert exported_2013["observation_coverage"] == "unknown"
    assert exported_2013["missing_data_status"] == "complete_assessed"


@pytest.mark.parametrize("bbox", [[34, 29, 40, 34], [34.8, 29, 39.4, 33.5], [34, 29, 43, 38]])
def test_country_exports_never_certify_larger_rectangles(bbox):
    sources = [_annual_country_source(2016, country=c) for c in ("Jordan", "Syria", "Lebanon")]
    result = analyze(query(complete_months=[], bbox=bbox), [], sources)
    row = month(result, "2016-01")
    assert row["count"] is None
    assert row["completeness"] == "unknown"
    assert row["anomaly_status"] == "incomplete_period"


@pytest.mark.parametrize(
    "filters",
    [
        {"start": "2026-01-15T00:00:00Z"},
        {"end": "2026-01-15T00:00:00Z"},
        {"start": "2026-01-01T12:00:00Z"},
        {"bbox": [35, 30, 36, 31]},
    ],
)
def test_api_audit_respects_actual_import_filters(filters):
    src = _api_window_source("filtered", SENSOR, "2026-01-01", 31)
    src["quality_report"]["filters"] = filters
    q = query(start_year=2026, end_year=2026, bbox=[34.8, 29, 39.4, 33.5], complete_months=[])
    row = month(analyze(q, [], [src]), "2026-01")
    assert row["count"] is None
    assert row["completeness"] == "unknown"


@pytest.mark.parametrize(
    "quality",
    [
        None,
        {},
        {"status": "validated", "invalid_rows": 0},
        {"status": "imported", "invalid_rows": 0, "source_sha256": "wrong", "filters": {}},
    ],
)
def test_source_url_without_matching_successful_import_is_not_completeness(quality):
    src = _annual_country_source(2016, quality_report=quality)
    q = query(bbox=None, polygon=JORDAN_COUNTRY_GEOJSON, complete_months=[])
    assert month(analyze(q, [], [src]), "2016-01")["count"] is None


def test_reimports_contribute_evidence_without_order_dependent_report_overwrites():
    import copy

    src = _api_window_source("reimported", SENSOR, "2026-01-01", 31)
    full = src.pop("quality_report")
    partial = copy.deepcopy(full)
    partial["filters"] = {"start": "2026-01-15T00:00:00Z"}
    q = query(start_year=2026, end_year=2026, bbox=[34.8, 29, 39.4, 33.5], complete_months=[])
    src["quality_reports"] = [partial, full]
    first = analyze(q, [], [src])
    assert month(first, "2026-01")["count"] == 0
    src["quality_reports"] = [full, partial]
    second = analyze(q, [], [src])
    assert month(second, "2026-01")["count"] == 0


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ({"metric": "reported_cell_days_per_1000km2_month"}, "unsupported_history_metric"),
        ({"metric": "observable_hotspot_cell_day_occupancy"}, "unsupported_history_metric"),
        ({"daynight": "D"}, "observation_stratum_or_grid_mismatch"),
        ({"grid_size_m": 5000}, "observation_stratum_or_grid_mismatch"),
        ({"bbox": [-125, 32, -114, 42]}, "geographic_scope_mismatch"),
        ({"confidence": "high"}, "confidence_scope_mismatch"),
        ({"end_year": 2015}, "temporal_scope_mismatch"),
        (
            {"versions": {"MODIS_AQUA": ["6.1"], "VIIRS_SNPP": ["2"]}},
            "product_version_transition_mismatch",
        ),
    ],
)
def test_supported_model_still_requires_compatible_metric_and_exact_validated_scope(
    mutation, reason
):
    from app.history import _verify_calibration_model
    from firescope_pipeline.calibration.models import fingerprint

    q = query(sensors=["MODIS_AQUA", "VIIRS_SNPP"], complete_months=[])
    scope = {
        "bbox": list(q.bbox),
        "polygon": None,
        "confidence": None,
        "start_year": 2013,
        "end_year": 2016,
    }
    context = {
        "history_scope": scope,
        "daynight": "all",
        "source": "VIIRS_SNPP",
        "reference": "MODIS_AQUA",
        "native_product_versions": {"MODIS_AQUA": ["6.2"], "VIIRS_SNPP": ["2"]},
    }
    core = {"method": "regression", "metric": HISTORY_METRIC, "context": context}

    def entry():
        artifact = {**core, "model_version": fingerprint(core)}
        return {
            "method": "regression",
            "status": "supported_for_scope",
            "artifact": artifact,
            "validation": {"status": "evaluated", "rejection_reasons": []},
        }

    versions = {"MODIS_AQUA": {"6.2"}, "VIIRS_SNPP": {"2"}}
    assert _verify_calibration_model(entry(), q, versions) == (True, None)
    for key, value in mutation.items():
        if key in scope:
            scope[key] = value
        elif key == "metric":
            core[key] = value
        elif key == "versions":
            context["native_product_versions"] = value
        else:
            context[key] = value
    assert _verify_calibration_model(entry(), q, versions) == (False, reason)
