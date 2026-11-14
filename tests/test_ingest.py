from datetime import UTC, datetime

import pytest

from firescope_pipeline.ingest import checksum, native_confidence, parse_csv


def test_preserves_source_values_and_unknown_frp(csv_bytes):
    rows = parse_csv(csv_bytes, "MODIS_TERRA", "6.1")
    assert rows[0]["raw_properties"]["acq_time"] == "0030"
    assert rows[0]["raw_properties"]["custom"] == "test-only"
    assert rows[0]["acquired_at"] == datetime(2024, 1, 1, 0, 30, tzinfo=UTC)
    assert rows[0]["confidence_native"] == "80"
    assert rows[0]["confidence_class"] == "high"
    assert rows[1]["frp_mw"] is None
    assert rows[1]["uncertainty"]["quantitative_uncertainty"] is None
    assert checksum(csv_bytes) == checksum(csv_bytes)
    assert checksum(csv_bytes) != checksum(csv_bytes + b"\n")


@pytest.mark.parametrize(("old", "new"), [
    ("0,0,", "91,0,"), ("0,0,", "0,181,"), ("0,0,", "nan,0,"),
    (",0030,", ",2460,"), (",0030,", ",999,"),
    (",80,", ",101,"), (",80,", ",nan,"), (",12.5,", ",-1,"),
    (",Terra,", ",Aqua,"), (",MODIS,", ",VIIRS,"), (",6.1,", ",6.0,"),
    (",D,", ",X,"),
])
def test_invalid_rows_rejected_atomically(csv_bytes, old, new):
    with pytest.raises(ValueError, match="Data row 1"):
        parse_csv(csv_bytes.replace(old.encode(), new.encode(), 1), "MODIS_TERRA", "6.1")


@pytest.mark.parametrize(("value", "expected"), [
    ("0", "low"), ("29", "low"), ("30", "nominal"), ("79", "nominal"),
    ("80", "high"), ("100", "high"),
])
def test_modis_class_boundaries(value, expected):
    assert native_confidence(value, "MODIS") == expected


def test_viirs_native_categories(csv_bytes):
    content = csv_bytes.replace(b"Terra", b"N").replace(b"MODIS", b"VIIRS")
    content = content.replace(b",80,", b",h,").replace(b",20,", b",n,")
    rows = parse_csv(content, "VIIRS_SNPP", "6.1")
    assert rows[0]["confidence_native"] == "h"
    assert rows[1]["confidence_class"] == "nominal"
    with pytest.raises(ValueError):
        native_confidence("80", "VIIRS")


@pytest.mark.parametrize("content", [
    b"", b"latitude,longitude\n", b"latitude,latitude\n1,2\n",
    b"latitude,longitude,acq_date,acq_time,confidence,satellite\n1,2,2024-01-01,0000,10,T,extra\n",
])
def test_invalid_file_shapes(content):
    with pytest.raises(ValueError):
        parse_csv(content, "MODIS_TERRA", "6.1")
