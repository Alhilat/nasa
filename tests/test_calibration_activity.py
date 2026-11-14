"""Synthetic geometry and numbers exercise algorithms, never scientific fire observations."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from firescope_pipeline.calibration.activity import aggregate_activity, grid_regions, pair_sensors


def region():
    return gpd.GeoDataFrame({"region_id": ["test_region"]}, geometry=[box(0, 0, 1000, 1000)], crs=6933)


def observations(rows):
    return pd.DataFrame(rows, columns=["sensor_code", "acquired_at", "longitude", "latitude", "daynight"])


def test_common_cell_day_deduplicates_pixel_counts_but_retains_sensor_counts():
    data = observations([
        ("MODIS_AQUA", "2024-01-01T01:00:00Z", .001, .001, "D"),
        ("VIIRS_SNPP", "2024-01-01T01:10:00Z", .001, .001, "D"),
        ("VIIRS_SNPP", "2024-01-01T01:11:00Z", .002, .002, "D"),
        ("VIIRS_SNPP", "2024-01-01T13:10:00Z", .002, .002, "D"),
    ])
    result = aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                                end="2024-02-01T00:00:00Z", grid_size_m=1000)
    assert result.monthly.hotspot_cell_days.tolist() == [1, 1]
    assert sorted(result.monthly.raw_detection_count.tolist()) == [1, 3]
    assert result.monthly.activity.tolist() == pytest.approx([1000, 1000])
    assert result.audit["missing_bins_imputed"] is False


def test_unobserved_month_is_not_zero_and_sensor_pair_remains_missing():
    data = observations([
        ("MODIS_AQUA", "2024-01-01T01:00:00Z", .001, .001, "D"),
        ("VIIRS_SNPP", "2024-02-01T01:00:00Z", .001, .001, "D"),
    ])
    result = aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                                end="2024-03-01T00:00:00Z", grid_size_m=1000)
    pairs = pair_sensors(result.monthly)
    assert len(pairs) == 2 and not pairs.paired.any()
    assert pairs.activity_source.isna().sum() == 1
    assert not (pairs.activity_source == 0).any()


def full_exposure():
    return pd.DataFrame([
        {"sensor_code": sensor, "day": f"2024-01-{day:02}", "grid_x": 0,
         "grid_y": 0, "daynight": "D", "observable": True}
        for sensor in ("MODIS_AQUA", "VIIRS_SNPP") for day in range(1, 32)
    ])


def test_primary_metric_only_creates_zero_from_explicit_common_exposure():
    data = observations([("MODIS_AQUA", "2024-01-01T01:00:00Z", .001, .001, "D")])
    result = aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                                end="2024-02-01T00:00:00Z", grid_size_m=1000, exposure=full_exposure())
    assert result.monthly.activity.tolist() == pytest.approx([1 / 31, 0])
    assert result.monthly.observability_fraction.tolist() == pytest.approx([1, 1])
    assert result.monthly.raw_detection_count.tolist() == [1, 0]
    assert pair_sensors(result.monthly).paired.all()


def test_primary_metric_handles_truly_zero_detections_without_inventing_exposure():
    result = aggregate_activity(observations([]), region(), start="2024-01-01T00:00:00Z",
                                end="2024-02-01T00:00:00Z", grid_size_m=1000, exposure=full_exposure())
    assert result.monthly.activity.tolist() == [0, 0]
    assert result.monthly.hotspot_cell_days.tolist() == [0, 0]


def test_partial_or_noncommon_exposure_cannot_be_compared_as_a_full_month():
    exposure = full_exposure()
    exposure.loc[(exposure.sensor_code == "VIIRS_SNPP") & (exposure.day > "2024-01-10"), "observable"] = False
    data = observations([("MODIS_AQUA", "2024-01-01T01:00:00Z", .001, .001, "D")])
    result = aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                                end="2024-02-01T00:00:00Z", grid_size_m=1000, exposure=exposure)
    assert result.monthly.activity.isna().all()
    assert result.monthly.observability_fraction.tolist() == pytest.approx([10/31, 10/31])


def test_no_common_cell_is_shared_across_region_folds():
    regions = gpd.GeoDataFrame({"region_id": ["a", "b"]}, geometry=[
        box(0, 0, 500, 1000), box(500, 0, 1000, 1000)], crs=6933)
    cells, excluded = grid_regions(regions, 1000)
    assert cells.empty
    assert excluded == 1


def test_overlapping_regions_and_duplicate_exposure_are_rejected():
    regions = gpd.GeoDataFrame({"region_id": ["a", "b"]}, geometry=[
        box(0, 0, 1000, 1000), box(500, 0, 1500, 1000)], crs=6933)
    with pytest.raises(ValueError, match="overlap"):
        grid_regions(regions, 1000)
    exposure = pd.concat([full_exposure(), full_exposure().iloc[:1]])
    data = observations([("MODIS_AQUA", "2024-01-01T01:00:00Z", .001, .001, "D")])
    with pytest.raises(ValueError, match="unique"):
        aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                           end="2024-02-01T00:00:00Z", grid_size_m=1000, exposure=exposure)


def test_naive_times_and_non_utc_month_starts_are_rejected():
    data = observations([("MODIS_AQUA", "2024-01-01T01:00:00", .001, .001, "D")])
    with pytest.raises(ValueError, match="timezones"):
        aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                           end="2024-02-01T00:00:00Z", grid_size_m=1000)
    with pytest.raises(ValueError, match="UTC month-start"):
        aggregate_activity(data, region(), start="2024-01-01T00:00:00+03:00",
                           end="2024-02-01T00:00:00+03:00", grid_size_m=1000)


def test_exposure_duplicates_after_date_normalization_are_rejected():
    exposure = full_exposure()
    duplicate = exposure.iloc[:1].copy()
    duplicate["day"] = "2024-1-1"
    data = observations([("MODIS_AQUA", "2024-01-01T01:00:00Z", .001, .001, "D")])
    with pytest.raises(ValueError, match="after normalization"):
        aggregate_activity(data, region(), start="2024-01-01T00:00:00Z",
                           end="2024-02-01T00:00:00Z", grid_size_m=1000,
                           exposure=pd.concat([exposure, duplicate]))
