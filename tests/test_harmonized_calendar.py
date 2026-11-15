"""Synthetic software fixtures only; never observations or operational calibration."""

import copy
import json
import math
import runpy
from pathlib import Path

import pytest
from app.calendar_schemas import HarmonizedCalendar
from app.harmonized_calendar import build_calendar

SENSORS = ["MODIS_AQUA", "VIIRS_SNPP"]
SOURCES = [
    {"id": s, "processing_level": "standard", "product_version": "synthetic"} for s in SENSORS
]


def row(sensor, month, count, *, complete=True):
    return {
        "sensor_code": sensor,
        "month": month,
        "count": count,
        "completeness": "complete" if complete else "unknown",
        "source_ids": [sensor],
        "missing_data_status": "complete_assessed" if complete else "unattested_or_missing_source",
    }


def overlap():
    rows = []
    for year in range(2013, 2017):
        for month in range(1, 13):
            source = 7 + (year - 2013) * 3 + month * 2 + (month % 3) ** 2
            reference = math.expm1(
                0.1 + 0.7 * math.log1p(source) + 0.1 * math.sin(2 * math.pi * (month - 1) / 12)
            )
            label = f"{year}-{month:02d}"
            rows.extend([row("MODIS_AQUA", label, reference), row("VIIRS_SNPP", label, source)])
    rows.extend(
        [
            row("VIIRS_SNPP", "2017-02", 25),
            row("MODIS_AQUA", "2017-02", None),
            row("VIIRS_SNPP", "2017-03", 10000),
            row("MODIS_AQUA", "2017-03", None),
            row("VIIRS_SNPP", "2017-04", None),
            row("MODIS_AQUA", "2017-04", None),
        ]
    )
    return rows


@pytest.fixture(scope="module")
def fitted():
    return build_calendar(overlap(), SOURCES, SENSORS)


def test_reuses_both_models_and_real_overlap_without_claiming_approval(fitted):
    assert fitted["status"] == "experimental"
    assert all(c["available"] for c in fitted["candidates"])
    assert {c["method"] for c in fitted["candidates"]} == {"regression", "quantile_mapping"}
    assert fitted["model"]["method"] == "regression"
    assert fitted["model"]["selection_year"] == 2016
    assert fitted["model"]["approval"] == "experimental"
    assert len(fitted["model"]["training_months"]) == 48
    assert fitted["model"]["artifact"]["metric"] == "monthly_normalized_detection_count"
    assert fitted["model"]["bootstrap_successes"] >= 50
    HarmonizedCalendar.model_validate(fitted)
    json.dumps(fitted, allow_nan=False)


def test_reference_precedence_mapping_gaps_bands_and_extrapolation(fitted):
    rows = {r["month"]: r for r in fitted["monthly"]}
    native = rows["2013-02"]
    assert native["origin"] == "modis_reference"
    assert native["value"] == next(
        r["count"]
        for r in overlap()
        if r["sensor_code"] == "MODIS_AQUA" and r["month"] == "2013-02"
    )
    assert native["lower_95"] is None  # No invented sensor error interval.
    mapped = rows["2017-02"]
    assert mapped["origin"] == "mapped_viirs"
    assert mapped["value"] > 0
    assert 0 <= mapped["lower_95"] <= mapped["upper_95"]
    assert mapped["source_ids"] == ["VIIRS_SNPP"]
    assert rows["2017-03"]["extrapolated"] is True
    assert rows["2017-03"]["lower_95"] is None
    assert rows["2017-03"]["upper_95"] is None
    assert rows["2017-04"]["value"] is None
    assert rows["2017-04"]["origin"] == "missing"


def test_deterministic_offline_replay_and_no_input_mutation(fitted):
    rows = overlap()
    original = copy.deepcopy(rows)
    again = build_calendar(list(reversed(rows)), list(reversed(SOURCES)), list(reversed(SENSORS)))
    assert again == fitted
    assert rows == original


def test_no_invented_zero_and_no_mapping_without_estimable_overlap():
    result = build_calendar(
        [
            row("MODIS_AQUA", "2014-01", None, complete=False),
            row("MODIS_AQUA", "2014-02", 0),
            row("VIIRS_SNPP", "2014-01", 50),
        ],
        SOURCES,
        SENSORS,
    )
    assert result["model"] is None
    assert result["monthly"][0]["value"] is None
    assert result["monthly"][1]["value"] == 0
    assert result["monthly"][1]["origin"] == "modis_reference"
    assert (
        build_calendar([row("VIIRS_SNPP", "2014-01", 50)], SOURCES, ["VIIRS_SNPP"])["monthly"][0][
            "value"
        ]
        is None
    )


def test_recent_partial_year_does_not_disable_supported_earlier_overlap():
    rows = overlap() + [row("MODIS_AQUA", "2026-01", 8), row("VIIRS_SNPP", "2026-01", 25)]
    result = build_calendar(rows, SOURCES, SENSORS)
    assert result["model"] is not None
    assert result["model"]["selection_year"] == 2016
    assert result["model"]["training_months"][-1] == "2026-01"


def test_conditional_counts_stay_experimental_and_nrt_is_excluded():
    rows = [row("MODIS_AQUA", "2014-01", 10, complete=False)]
    result = build_calendar(rows, SOURCES, SENSORS)
    assert result["monthly"][0]["value"] == 10
    assert result["monthly"][0]["completeness"] == "unknown"
    assert result["monthly"][0]["validation_status"] == "experimental"
    assert "conditional" in result["monthly"][0]["reason"]
    nrt = [{**s, "processing_level": "nrt"} for s in SOURCES]
    assert build_calendar(rows, nrt, SENSORS)["monthly"][0]["value"] is None


def test_approved_scope_can_validate_mapping_but_never_extrapolation(fitted):
    artifact = fitted["model"]["artifact"]
    approved = [
        {
            "artifact": artifact,
            "method": artifact["method"],
            "model_version": artifact["model_version"],
        }
    ]
    rows = [row("VIIRS_SNPP", "2017-02", 25), row("MODIS_AQUA", "2017-02", None)]
    result = build_calendar(rows, SOURCES, SENSORS, approved_models=approved)
    assert result["status"] == "validated"
    assert result["monthly"][0]["validation_status"] == "validated"
    assert result["monthly"][0]["lower_95"] is None
    assert "training rows unavailable" in result["monthly"][0]["uncertainty_reason"]
    rows[0]["count"] = 100000
    result = build_calendar(rows, SOURCES, SENSORS, approved_models=approved)
    assert result["status"] == "experimental"
    assert result["monthly"][0]["validation_status"] == "experimental"


def test_frontend_contract_is_generated_from_backend_schema():
    root = Path(__file__).resolve().parents[1]
    generator = runpy.run_path(str(root / "scripts/generate_calendar_types.py"))
    assert generator["OUTPUT"].read_text(encoding="utf-8") == generator["render_types"]()


def test_harmonized_median_context_keeps_experimental_maps_out_of_reference_baselines(fitted):
    rows = {r["month"]: r for r in fitted["monthly"]}
    assert rows["2017-02"]["median_comparison"]["status"] == "unapproved_mapping"
    assert rows["2017-02"]["median_comparison"]["departure"] is None
    assert rows["2017-03"]["median_comparison"]["status"] == "extrapolated"


def test_reference_selection_prefers_longer_pre_aqua_coverage_and_exposes_mapped_overlap():
    rows = [row("MODIS_TERRA", "2000-11", 12), row("MODIS_TERRA", "2000-12", 18)]
    for year in range(2013, 2017):
        for m in range(1, 13):
            source = 7 + (year - 2013) * 3 + m * 2 + (m % 3) ** 2
            ref = math.expm1(0.1 + 0.7 * math.log1p(source) + 0.1 * math.sin(2 * math.pi * (m - 1) / 12))
            label = f"{year}-{m:02d}"
            rows.extend([
                row("MODIS_TERRA", label, ref),
                row("MODIS_AQUA", label, ref),
                row("VIIRS_SNPP", label, source),
            ])
    rows.append(row("VIIRS_SNPP", "2017-02", 25))
    sensors = ["MODIS_TERRA", "MODIS_AQUA", "VIIRS_SNPP"]
    sources = [{"id": s, "processing_level": "standard", "product_version": "synthetic"} for s in sensors]
    result = build_calendar(rows, sources, sensors)
    assert result["reference_sensor"] == "MODIS_TERRA"
    by_month = {r["month"]: r for r in result["monthly"]}
    assert by_month["2000-11"]["origin"] == "modis_reference"
    assert by_month["2000-11"]["value"] == 12
    assert by_month["2013-02"]["origin"] == "modis_reference"
    assert by_month["2013-02"]["mapped_value"] > 0
    assert 0 <= by_month["2013-02"]["mapped_lower_95"] <= by_month["2013-02"]["mapped_upper_95"]
