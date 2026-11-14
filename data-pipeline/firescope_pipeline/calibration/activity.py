"""Common equal-area grid and UTC cell-day activity, retaining sensor identity."""
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import box

METRIC_VERSION = "equal-area-cell-day-v1"
CRS = "EPSG:6933"


@dataclass
class ActivityResult:
    monthly: pd.DataFrame
    cells: gpd.GeoDataFrame
    audit: dict


def grid_regions(regions: gpd.GeoDataFrame, grid_size_m: int = 5000):
    if not 1000 <= grid_size_m <= 50000:
        raise ValueError("Common grid size must be 1–50 km")
    if regions.crs is None or "region_id" not in regions or regions.region_id.duplicated().any():
        raise ValueError("Regions need a CRS and unique region_id values")
    if regions.empty or regions.geometry.is_empty.any() or not regions.geometry.is_valid.all():
        raise ValueError("Regions must contain valid nonempty polygons")
    if not regions.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Regions must be Polygon/MultiPolygon geometries")
    projected = regions.to_crs(CRS).sort_values("region_id")
    bounds = regions.to_crs("EPSG:4326").total_bounds
    if bounds[1] < -86 or bounds[3] > 86:
        raise ValueError("EPSG:6933 study regions must stay within 86 degrees latitude")
    for index, geometry in enumerate(projected.geometry):
        for other in projected.geometry.iloc[index + 1:]:
            if geometry.intersection(other).area > 1:
                raise ValueError("Study regions must not overlap in area")
    west, south, east, north = projected.total_bounds
    xs = np.arange(np.floor(west / grid_size_m), np.ceil(east / grid_size_m), dtype=int)
    ys = np.arange(np.floor(south / grid_size_m), np.ceil(north / grid_size_m), dtype=int)
    if len(xs) * len(ys) > 200000:
        raise ValueError("Study grid exceeds 200,000 cells; use coarser cells or smaller regions")
    xx, yy = np.meshgrid(xs, ys)
    cells = gpd.GeoDataFrame({"grid_x": xx.ravel(), "grid_y": yy.ravel()}, geometry=box(
        xx.ravel() * grid_size_m, yy.ravel() * grid_size_m,
        (xx.ravel() + 1) * grid_size_m, (yy.ravel() + 1) * grid_size_m,
    ), crs=CRS)
    intersections = gpd.overlay(cells, projected[["region_id", "geometry"]], how="intersection")
    intersections["area_km2"] = intersections.area / 1e6
    intersections = intersections[intersections.area_km2 > 1e-8]
    # Exclude cells intersecting multiple held-out regions, rather than sharing their observations.
    counts = intersections.groupby(["grid_x", "grid_y"]).region_id.nunique()
    shared = set(counts[counts > 1].index)
    keep = [key not in shared for key in zip(intersections.grid_x, intersections.grid_y)]
    return intersections.loc[keep].reset_index(drop=True), len(shared)


def aggregate_activity(observations: pd.DataFrame, regions: gpd.GeoDataFrame, *,
                       start: str, end: str, grid_size_m=5000, exposure: pd.DataFrame | None = None,
                       paired_sensors=("VIIRS_SNPP", "MODIS_AQUA"), min_coverage=0.8):
    """No absent detection bin is interpreted as an observed zero without supplied exposure.

    Exposure rows: sensor_code,day,grid_x,grid_y,daynight,observable (strict Boolean).
    An observable row asserts curated sufficient visibility for that full common cell-day/stratum.
    """
    start_time, end_time = pd.Timestamp(start), pd.Timestamp(end)
    if start_time.tzinfo is None or end_time.tzinfo is None or start_time >= end_time:
        raise ValueError("Use timezone-aware month-start boundaries with start < end")
    start_time, end_time = start_time.tz_convert("UTC"), end_time.tz_convert("UTC")
    if (start_time.day != 1 or end_time.day != 1 or start_time != start_time.normalize()
            or end_time != end_time.normalize()):
        raise ValueError("Use UTC month-start boundaries")
    if not 0 < min_coverage <= 1:
        raise ValueError("min_coverage must be in (0,1]")
    cells, shared = grid_regions(regions, grid_size_m)
    work = observations.copy()
    required = {"sensor_code", "acquired_at", "latitude", "longitude", "daynight"}
    if not required <= set(work):
        raise ValueError("Normalized observations lack required activity fields")
    numeric = work[["latitude", "longitude"]].to_numpy(dtype=float)
    if (not np.isfinite(numeric).all() or not work.latitude.between(-90, 90).all()
            or not work.longitude.between(-180, 180).all()):
        raise ValueError("Invalid WGS84 coordinates")
    if not work.acquired_at.map(lambda value: pd.Timestamp(value).tzinfo is not None).all():
        raise ValueError("Observation acquisition timestamps must have explicit timezones")
    work["acquired_at"] = pd.to_datetime(work.acquired_at, utc=True, errors="raise")
    work = work[(work.acquired_at >= start_time) & (work.acquired_at < end_time)].copy()
    unknown_daynight = int((~work.daynight.isin(["D", "N"])).sum())
    work = work[work.daynight.isin(["D", "N"])].copy()
    points = gpd.GeoDataFrame(work, geometry=gpd.points_from_xy(work.longitude, work.latitude),
                             crs="EPSG:4326").to_crs(CRS)
    points["grid_x"] = np.floor(points.geometry.x / grid_size_m).astype(int)
    points["grid_y"] = np.floor(points.geometry.y / grid_size_m).astype(int)
    points["day"] = points.acquired_at.dt.strftime("%Y-%m-%d")
    points["month"] = points.acquired_at.dt.strftime("%Y-%m")
    points = points.merge(cells[["grid_x", "grid_y", "region_id", "area_km2"]],
                          on=["grid_x", "grid_y"], how="inner")
    not_in_retained_grid = len(work) - len(points)
    # A border cell may extend outside the supplied study geometry; only retain interior detections.
    union = regions.to_crs(CRS).geometry.union_all()
    outside_boundary = int((~points.geometry.covered_by(union)).sum())
    points = points[points.geometry.covered_by(union)].copy()
    raw_counts = points.groupby(["sensor_code", "region_id", "month", "daynight"]).size()
    version_sets = None
    if "product_version" in points:
        version_sets = points.groupby(["sensor_code", "region_id", "month", "daynight"])[
            "product_version"].agg(lambda values: "|".join(sorted(set(str(v) for v in values))))
    active = pd.DataFrame(points.drop_duplicates(
        ["sensor_code", "day", "grid_x", "grid_y", "daynight"],
    ).drop(columns="geometry"))
    keys = ["sensor_code", "region_id", "month", "daynight"]
    if active.empty and exposure is None:
        raise ValueError("No detections remain in the selected grid, interval and strata")
    areas = cells.groupby("region_id").area_km2.sum()
    if exposure is None:
        result = active.groupby(keys).agg(hotspot_cell_days=("day", "size")).reset_index()
        result["activity"] = result.hotspot_cell_days * 1000 / result.region_id.map(areas)
        result["exposure_area_days_km2"] = np.nan
        result["metric"] = "reported_cell_days_per_1000km2_month"
        mode = "detection_only_conditional"
    else:
        exposure_keys = ["sensor_code", "day", "grid_x", "grid_y", "daynight"]
        if not {*exposure_keys, "observable"} <= set(exposure):
            raise ValueError("Exposure manifest lacks required cell-day fields")
        exp = exposure.copy()
        for column in ("grid_x", "grid_y"):
            values = pd.to_numeric(exp[column], errors="raise")
            if not np.isfinite(values).all() or not (values == np.floor(values)).all():
                raise ValueError("Exposure grid indices must be finite integers")
            exp[column] = values.astype(int)
        if exp.duplicated(exposure_keys).any():
            raise ValueError("Exposure cell-day keys must be unique")
        if exp.observable.isna().any() or not exp.observable.map(lambda x: isinstance(x, (bool, np.bool_))).all():
            raise ValueError("observable must be true/false Boolean, never an inferred detection flag")
        if not exp.daynight.isin(["D", "N"]).all():
            raise ValueError("Exposure daynight must be D or N")
        exp["day"] = pd.to_datetime(exp.day, format="%Y-%m-%d", errors="raise").dt.strftime("%Y-%m-%d")
        if exp.duplicated(exposure_keys).any():
            raise ValueError("Exposure cell-day keys must be unique after normalization")
        exp = exp[(exp.day >= start_time.strftime("%Y-%m-%d")) &
                  (exp.day < end_time.strftime("%Y-%m-%d")) & exp.observable].copy()
        exp = exp[exp.sensor_code.isin(paired_sensors)]
        support_keys = ["day", "grid_x", "grid_y", "daynight"]
        shared_support = exp.groupby(support_keys).sensor_code.nunique()
        support = shared_support[shared_support == len(set(paired_sensors))].reset_index()[support_keys]
        exp = exp.merge(support, on=support_keys, how="inner")
        exp = exp.merge(cells[["grid_x", "grid_y", "region_id", "area_km2"]],
                        on=["grid_x", "grid_y"], how="inner")
        exp["month"] = exp.day.str[:7]
        exp = exp.merge(active[exposure_keys].assign(active=True), on=exposure_keys, how="left")
        exp["active_area_days"] = np.where(exp.active.eq(True), exp.area_km2, 0)
        result = exp.groupby(keys).agg(
            active_area_days_km2=("active_area_days", "sum"),
            exposure_area_days_km2=("area_km2", "sum"), hotspot_cell_days=("active", "count"),
        ).reset_index()
        result["activity"] = result.active_area_days_km2 / result.exposure_area_days_km2
        result["metric"] = "observable_hotspot_cell_day_occupancy"
        mode = "provided_observability"
    result = result.merge(raw_counts.rename("raw_detection_count").reset_index(), on=keys, how="left")
    if version_sets is not None:
        result = result.merge(version_sets.rename("product_versions").reset_index(), on=keys, how="left")
    # Zero raw counts are defensible only for explicitly observable exposure bins.
    if exposure is not None:
        result["raw_detection_count"] = result.raw_detection_count.fillna(0).astype(int)
    result["study_area_km2"] = result.region_id.map(areas)
    if exposure is not None:
        days = pd.to_datetime(result.month + "-01").dt.days_in_month
        result["observability_fraction"] = result.exposure_area_days_km2 / (result.study_area_km2 * days)
        result.loc[result.observability_fraction < min_coverage, "activity"] = np.nan
    result["year"] = result.month.str[:4].astype(int)
    result["month_number"] = result.month.str[5:7].astype(int)
    result["coverage_mode"] = mode
    audit = {"metric_version": METRIC_VERSION, "crs": CRS, "grid_size_m": grid_size_m,
             "shared_boundary_cells_excluded": shared, "input_rows": len(observations),
             "retained_detection_rows": len(points), "unknown_daynight_excluded": unknown_daynight,
             "detections_outside_retained_grid": not_in_retained_grid,
             "detections_outside_boundary_within_grid": outside_boundary,
             "region_areas_km2": {str(k): float(v) for k, v in areas.items()},
             "coverage_mode": mode, "missing_bins_imputed": False,
             "min_common_observability_fraction": min_coverage,
             "not_unique_fires": True, "not_burned_area": True}
    return ActivityResult(result.sort_values(keys).reset_index(drop=True), cells, audit)


def pair_sensors(monthly, source="VIIRS_SNPP", reference="MODIS_AQUA", daynight="D"):
    if source == reference or daynight not in {"D", "N"}:
        raise ValueError("Choose distinct sensors and a single day/night stratum")
    frame = monthly[monthly.daynight == daynight]
    keys = ["region_id", "month", "year", "month_number", "metric", "coverage_mode"]
    if frame.duplicated(["sensor_code", *keys]).any():
        raise ValueError("Activity rows must be unique per sensor/region/month/stratum")
    left = frame[frame.sensor_code == source][keys + ["activity", "raw_detection_count"]]
    right = frame[frame.sensor_code == reference][keys + ["activity", "raw_detection_count"]]
    if "product_versions" in frame:
        left = frame[frame.sensor_code == source][keys + ["activity", "raw_detection_count", "product_versions"]]
        right = frame[frame.sensor_code == reference][keys + ["activity", "raw_detection_count", "product_versions"]]
    result = left.merge(right, on=keys, how="outer", suffixes=("_source", "_reference"), indicator=True)
    result["paired"] = (result._merge == "both") & result.activity_source.notna() & result.activity_reference.notna()
    return result.drop(columns="_merge").sort_values(["region_id", "month"]).reset_index(drop=True)
