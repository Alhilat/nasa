"""All rows here are synthetic software fixtures, not scientific observations."""
import argparse
import json
from datetime import UTC, datetime

import pytest

from firescope_pipeline.cli import main, selection_from_args
from firescope_pipeline.ingest import inspect_csv
from firescope_pipeline.selection import JORDAN_BBOX, Selection
from firescope_pipeline.service import import_source

HEADER = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp,version,daynight,bright_t31\n"


def payload(*rows):
    return (HEADER + "\n".join(rows) + ("\n" if rows else "")).encode()


def test_combined_modis_and_jordan_overlap_filters_preserve_all_raw():
    content = payload(
        "31,36,2013-01-01,0000,T,MODIS,80,0,6.1,D,290",
        "31,36,2025-12-31,2359,A,MODIS,50,,6.1,N,290",
        "31,36,2012-12-31,2359,T,MODIS,80,5,6.1,D,290",
        "0,0,2024-01-01,0000,T,MODIS,80,5,6.1,D,290",
    )
    selection = selection_from_args(argparse.Namespace(profile="jordan"))
    batch = inspect_csv(content, "MODIS", "6.1", selection)
    assert len(batch.raw) == 4
    assert [row["sensor_code"] for row in batch.selected] == ["MODIS_TERRA", "MODIS_AQUA"]
    assert batch.report["excluded_rows"] == 2
    assert batch.report["selected_missing_frp"] == 1
    assert batch.selected[0]["frp_mw"] == 0
    assert batch.raw[0]["raw_properties"]["bright_t31"] == "290"


def test_validation_retains_invalid_rows_for_explicit_quarantine():
    batch = inspect_csv(payload(
        "31,36,2024-01-01,0000,T,MODIS,80,1,6.1,D,290",
        "91,36,2024-01-01,0000,T,MODIS,80,1,6.1,D,290",
    ), "MODIS", "6.1")
    assert batch.report["invalid_rows"] == 1
    assert len(batch.raw) == 2
    assert len(batch.selected) == 1
    assert batch.report["issue_samples"][0]["source_row"] == 2
    assert "raw_properties" not in batch.selected[0]  # Separate normalized payload.


def test_duplicates_revisions_and_missingness_are_reported_conservatively():
    first = "31,36,2024-01-01,0000,T,MODIS,80,1,6.1,D,290"
    batch = inspect_csv(payload(first, first, first.replace(",1,6.1,", ",2,6.1,")), "MODIS", "6.1")
    assert batch.report["within_file_exact_duplicates"] == 1
    assert batch.report["within_file_same_sensor_time_position_repeats"] == 2
    assert len(batch.selected) == 3  # Database identity resolution owns de-duplication.


def test_header_only_is_a_valid_zero_detection_response():
    batch = inspect_csv(payload(), "MODIS", "native")
    assert batch.report["source_rows"] == 0
    assert batch.selected == []
    assert batch.report["coverage_known"] is False


def test_standard_processing_rejects_nrt_version_and_reports_observed_versions():
    content = payload("31,36,2024-01-01,0000,T,MODIS,80,1,6.1NRT,D,290")
    batch = inspect_csv(content, "MODIS", "native", processing_level="standard")
    assert batch.report["invalid_rows"] == 1
    assert batch.report["status"] == "validation_failed"
    assert batch.report["observed_product_versions"] == {"6.1NRT": 1}


@pytest.mark.parametrize("field,value", [
    ("latitude", "inf"), ("longitude", "-181"), ("frp", "nan"), ("frp", "-999"),
    ("acq_date", "2023-02-29"), ("acq_time", "2360"), ("acq_time", "2400"),
    ("satellite", "N"), ("instrument", "VIIRS"), ("bright_t31", "-1"),
])
def test_quality_report_identifies_invalid_scientific_fields(field, value):
    keys = HEADER.strip().split(",")
    row = dict(zip(keys, "31,36,2024-01-01,0000,T,MODIS,80,1,6.1,D,290".split(",")))
    row[field] = value
    batch = inspect_csv(payload(",".join(row[key] for key in keys)), "MODIS", "6.1")
    assert batch.report["invalid_rows"] == 1
    assert not batch.selected


def test_viirs_fields_unknown_columns_and_versions_remain_native():
    content = ("latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp,version,"
               "bright_ti4,bright_ti5,type,extra\n"
               "31,36,2024-01-01,30,N,VIIRS,h,,2.0,320,290,0,original\n").encode()
    batch = inspect_csv(content, "VIIRS_SNPP", "native")
    raw = batch.raw[0]["raw_properties"]
    assert raw["acq_time"] == "30"
    assert raw["version"] == "2.0"
    assert raw["extra"] == "original"
    assert batch.selected[0]["acquired_at"] == datetime(2024, 1, 1, 0, 30, tzinfo=UTC)
    assert batch.selected[0]["frp_mw"] is None


def test_polygon_holes_boundaries_and_end_exclusive():
    selection = Selection(polygon={"type": "Polygon", "coordinates": [
        [[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]],
        [[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]],
    ]}, end=datetime(2024, 1, 2, tzinfo=UTC))
    row = {"longitude": 0, "latitude": 0, "acquired_at": datetime(2024, 1, 1, tzinfo=UTC)}
    assert selection.includes(row)
    assert not selection.includes({**row, "longitude": 1.5, "latitude": 1.5})
    assert not selection.includes({**row, "acquired_at": selection.end})
    assert Selection(bbox=(170, -10, -170, 10)).includes({**row, "longitude": 179})


def test_recent_profile_does_not_apply_historical_years():
    selection = selection_from_args(argparse.Namespace(profile="jordan"), historical=False)
    assert selection.bbox == JORDAN_BBOX
    assert selection.start is None and selection.end is None


def test_quality_report_counts_all_errors_but_bounds_samples():
    batch = inspect_csv(payload(*(["91,36,2024-01-01,0000,T,MODIS,80,1,6.1,D,290"] * 105)),
                        "MODIS", "6.1")
    assert batch.report["invalid_rows"] == 105
    assert len(batch.report["issue_samples"]) == 100
    assert batch.report["issue_samples_truncated"]
    assert sum(batch.report["issue_counts"].values()) == 105


def test_validate_cli_writes_report_without_database(tmp_path, monkeypatch, capsys):
    source = tmp_path / "test-only.csv"
    source.write_bytes(payload("91,36,2024-01-01,0000,T,MODIS,80,1,6.1,D,290"))
    report = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["firescope-pipeline", "validate", str(source),
                                     "--sensor", "MODIS", "--product-version", "6.1",
                                     "--report", str(report)])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 1
    assert json.loads(report.read_text())["invalid_rows"] == 1
    assert "invalid_rows" in capsys.readouterr().out


def test_key_bearing_source_url_is_rejected_before_persistence():
    with pytest.raises(ValueError, match="key-bearing") as error:
        import_source(None, b"", filename="test.csv", sensor="MODIS", product_version="native",
                      processing_level="nrt", retrieved_at=datetime.now(UTC),
                      source_url="https://firms.modaps.eosdis.nasa.gov/api/area/csv/testkey/MODIS_NRT/world/1")
    assert "testkey" not in str(error.value)
