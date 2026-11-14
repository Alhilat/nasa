import math

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import box

ALGORITHM_VERSION = "wgs84-grid-daily-v2"


def validate_grid(grid_size: float):
    if not math.isfinite(grid_size) or not 0.01 <= grid_size <= 5:
        raise ValueError("Grid size must be finite and between 0.01 and 5 degrees")
    if not math.isclose(180 / grid_size, round(180 / grid_size), abs_tol=1e-7):
        raise ValueError("Grid size must divide 180 degrees exactly (e.g. 0.25, 0.5, 1)")


def aggregate_frame(frame: pd.DataFrame, grid_size: float) -> gpd.GeoDataFrame:
    """Common grid/day summaries, stratified by sensor; no sensor-bias correction."""
    validate_grid(grid_size)
    if frame.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    work = frame.copy()
    # Include +180/+90 in the last cell, never create a cell outside the world.
    work["grid_x"] = np.minimum(
        np.floor((work.longitude + 180) / grid_size), round(360 / grid_size) - 1,
    ).astype(int)
    work["grid_y"] = np.minimum(
        np.floor((work.latitude + 90) / grid_size), round(180 / grid_size) - 1,
    ).astype(int)
    work["day"] = pd.to_datetime(work.acquired_at, utc=True).dt.date
    grouped = work.groupby(["sensor_code", "day", "grid_x", "grid_y"], sort=True)
    result = grouped.agg(
        detection_count=("id", "size"), frp_known_count=("frp_mw", "count"),
    ).reset_index()
    # A bin whose FRP is entirely missing stays unknown, never zero.
    result["frp_sum_mw"] = grouped.frp_mw.sum(min_count=1).to_numpy()
    result["grid_size_deg"] = grid_size
    west = result.grid_x.to_numpy() * grid_size - 180
    south = result.grid_y.to_numpy() * grid_size - 90
    geometry = box(west, south, west + grid_size, south + grid_size)
    return gpd.GeoDataFrame(result, geometry=geometry, crs="EPSG:4326")
