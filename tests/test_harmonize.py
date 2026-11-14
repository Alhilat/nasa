from datetime import date

import pandas as pd
import pytest

from firescope_pipeline.harmonize import aggregate_frame


def test_sensor_separation_frp_missingness_and_utc_bins():
    # Explicitly synthetic software test coordinates and values.
    frame = pd.DataFrame([
        {"id": 1, "sensor_code": "MODIS_TERRA", "latitude": 0.1, "longitude": 0.1,
         "acquired_at": "2024-01-02T00:30:00+02:00", "frp_mw": None},
        {"id": 2, "sensor_code": "MODIS_TERRA", "latitude": 0.2, "longitude": 0.2,
         "acquired_at": "2024-01-01T23:30:00Z", "frp_mw": None},
        {"id": 3, "sensor_code": "VIIRS_SNPP", "latitude": 0.1, "longitude": 0.1,
         "acquired_at": "2024-01-01T23:30:00Z", "frp_mw": 3.0},
    ])
    result = aggregate_frame(frame, 0.25)
    assert len(result) == 2
    modis = result[result.sensor_code == "MODIS_TERRA"].iloc[0]
    assert modis.day == date(2024, 1, 1)
    assert modis.detection_count == 2
    assert modis.frp_known_count == 0
    assert pd.isna(modis.frp_sum_mw)
    assert modis.geometry.bounds == (0, 0, 0.25, 0.25)
    assert result.crs.to_epsg() == 4326


def test_positive_world_edges_stay_within_domain():
    frame = pd.DataFrame([{
        "id": 1, "sensor_code": "VIIRS_SNPP", "latitude": 90, "longitude": 180,
        "acquired_at": "2024-01-01T00:00:00Z", "frp_mw": 0,
    }])
    result = aggregate_frame(frame, 0.25).iloc[0]
    assert result.geometry.bounds == (179.75, 89.75, 180, 90)
    assert result.frp_sum_mw == 0


@pytest.mark.parametrize("size", [0, -1, float("nan"), float("inf"), 6, 0.7])
def test_invalid_grid_rejected(size):
    with pytest.raises(ValueError):
        aggregate_frame(pd.DataFrame(), size)


def test_empty_archive_produces_no_invented_bins():
    assert aggregate_frame(pd.DataFrame(), 0.25).empty


def test_archive_with_only_missing_frp_preserves_unknown():
    frame = pd.DataFrame([{
        "id": 1, "sensor_code": "MODIS_TERRA", "latitude": 0, "longitude": 0,
        "acquired_at": "2024-01-01T00:00:00Z", "frp_mw": None,
    }])
    result = aggregate_frame(frame, 0.25).iloc[0]
    assert pd.isna(result.frp_sum_mw)
    assert result.frp_known_count == 0
