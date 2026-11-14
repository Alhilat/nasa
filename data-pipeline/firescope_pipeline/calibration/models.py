"""Baseline, seasonal log-linear regression and empirical seasonal quantile mapping."""
import hashlib
import json

import numpy as np
import pandas as pd

MODEL_VERSION = "sensor-calibration-v1"
METHODS = ("baseline", "regression", "quantile_mapping")


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def design(x, month):
    angle = 2 * np.pi * (np.asarray(month, dtype=float) - 1) / 12
    return np.column_stack([np.ones(len(x)), np.log1p(x), np.sin(angle), np.cos(angle),
                            np.sin(2 * angle), np.cos(2 * angle)])


def _quantile_parameters(x, y):
    probabilities = np.linspace(0, 1, 101)
    qx = np.quantile(x, probabilities, method="linear")
    qy = np.quantile(y, probabilities, method="linear")
    # A repeated source quantile has a deterministic midrank target; no random tie breaking.
    unique, inverse = np.unique(qx, return_inverse=True)
    mapped = np.array([qy[inverse == index].mean() for index in range(len(unique))])
    return {"x": unique.tolist(), "y": mapped.tolist(), "n": len(x)}


def fit_model(train: pd.DataFrame, method: str, *, metric: str, context=None):
    if method not in METHODS:
        raise ValueError("Unsupported calibration method")
    x, y = train.activity_source.to_numpy(float), train.activity_reference.to_numpy(float)
    months = train.month_number.to_numpy(int)
    if (len(x) < 12 or not np.isfinite(x).all() or not np.isfinite(y).all()
            or (x < 0).any() or (y < 0).any() or not ((months >= 1) & (months <= 12)).all()):
        raise ValueError("Need at least 12 finite nonnegative training pairs and valid months")
    if method != "baseline" and (len(np.unique(x)) < 3 or len(np.unique(y)) < 3):
        raise ValueError("Calibration requires at least three distinct activities in each sensor")
    if metric == "observable_hotspot_cell_day_occupancy" and ((x > 1).any() or (y > 1).any()):
        raise ValueError("Cell-day occupancy must remain in [0,1]")
    parameters = {}
    if method == "regression":
        matrix = design(x, months)
        if np.linalg.matrix_rank(matrix) < matrix.shape[1]:
            raise ValueError("Insufficient seasonal/input variation for regression")
        coefficients = np.linalg.lstsq(matrix, np.log1p(y), rcond=None)[0]
        if coefficients[1] < 0:
            raise ValueError("Negative sensor-response slope is not accepted")
        parameters = {"coefficients": coefficients.tolist(), "response": "log1p",
                      "features": ["intercept", "log1p_source", "sin1", "cos1", "sin2", "cos2"]}
    elif method == "quantile_mapping":
        parameters = {"global": _quantile_parameters(x, y), "seasons": {},
                      "tail_policy": "clip_and_flag", "quantile_method": "linear",
                      "tie_policy": "mean_target_of_tied_source_quantiles"}
        for quarter in range(1, 5):
            subset = ((months - 1) // 3 + 1) == quarter
            if subset.sum() >= 8 and len(np.unique(x[subset])) >= 3:
                parameters["seasons"][str(quarter)] = _quantile_parameters(x[subset], y[subset])
            else:
                parameters["seasons"][str(quarter)] = {"fallback": "global", "n": int(subset.sum())}
    audit_columns = [c for c in ("region_id", "month", "activity_source", "activity_reference") if c in train]
    core = {
        "algorithm_version": MODEL_VERSION, "method": method, "metric": metric,
        "training_pairs": len(train), "training_hash": fingerprint(
            train[audit_columns].sort_values(audit_columns[:2]).to_dict(orient="records")),
        "training_years": sorted(int(v) for v in train.year.unique()),
        "training_regions": sorted(str(v) for v in train.region_id.unique()),
        "source_range": [float(x.min()), float(x.max())], "parameters": parameters,
        "context": context or {}, "bounded_occupancy": metric == "observable_hotspot_cell_day_occupancy",
    }
    return {**core, "model_version": fingerprint(core)}


def predict_model(model: dict, frame: pd.DataFrame):
    x = frame.activity_source.to_numpy(float)
    months = frame.month_number.to_numpy(int)
    output = np.full(len(x), np.nan)
    extrapolated = np.zeros(len(x), dtype=bool)
    valid = np.isfinite(x) & (x >= 0) & (months >= 1) & (months <= 12)
    low, high = model["source_range"]
    extrapolated[valid] = (x[valid] < low) | (x[valid] > high)
    if model["method"] == "baseline":
        output[valid] = x[valid]
    elif model["method"] == "regression":
        z = design(x[valid], months[valid]) @ np.array(model["parameters"]["coefficients"])
        output[valid] = np.maximum(0, np.expm1(np.clip(z, -50, 50)))
    elif model["method"] == "quantile_mapping":
        for index in np.flatnonzero(valid):
            season = model["parameters"]["seasons"][str((months[index] - 1) // 3 + 1)]
            parameters = model["parameters"]["global"] if "fallback" in season else season
            knots = parameters["x"]
            output[index] = np.interp(x[index], knots, parameters["y"])
            extrapolated[index] = x[index] < knots[0] or x[index] > knots[-1]
    else:
        raise ValueError("Unsupported model artifact")
    if model["bounded_occupancy"]:
        output = np.clip(output, 0, 1)
    return output, extrapolated
