"""Blocked validation, fixed protocol gates, agreement metrics and statistical uncertainty."""
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from firescope_pipeline.calibration.models import METHODS, fit_model, predict_model


@dataclass(frozen=True)
class ValidationProtocol:
    train_years: tuple[int, ...]
    validation_years: tuple[int, ...]
    test_years: tuple[int, ...]
    heldout_regions: tuple[str, ...]
    seed: int = 2026
    bootstrap_repeats: int = 200
    min_training_pairs: int = 24
    min_evaluation_pairs: int = 8
    min_trend_months: int = 6
    min_improvement: float = 0.10
    max_extrapolation_fraction: float = 0.10

    def validate(self, regions):
        integers = (self.seed, self.bootstrap_repeats, self.min_training_pairs,
                    self.min_evaluation_pairs, self.min_trend_months,
                    *self.train_years, *self.validation_years, *self.test_years)
        if any(type(value) is not int for value in integers):
            raise ValueError("Protocol years, seed and sample/bootstrap counts must be integers")
        if self.min_training_pairs < 12 or self.min_evaluation_pairs < 1 or not 1 <= self.min_trend_months <= 12:
            raise ValueError("Invalid protocol sample or trend-support thresholds")
        sets = [set(self.train_years), set(self.validation_years), set(self.test_years)]
        if (any(not s for s in sets) or any(sets[i] & sets[j] for i in range(3) for j in range(i+1,3))
                or max(sets[0]) >= min(sets[1]) or max(sets[1]) >= min(sets[2])):
            raise ValueError("Training, validation and test years must be disjoint and chronological")
        if not set(self.heldout_regions) < set(regions) or not self.heldout_regions:
            raise ValueError("Hold out at least one region and leave at least one training region")
        if (not 20 <= self.bootstrap_repeats <= 2000 or not 0 < self.min_improvement < 1
                or not 0 <= self.max_extrapolation_fraction <= 1):
            raise ValueError("Invalid bootstrap or acceptance configuration")


def metrics(reference, prediction):
    reference, prediction = np.asarray(reference, float), np.asarray(prediction, float)
    valid = np.isfinite(reference) & np.isfinite(prediction)
    if not valid.any():
        return {"n": 0, "mae": None, "rmse": None, "bias": None}
    error = prediction[valid] - reference[valid]
    return {"n": int(valid.sum()), "mae": float(np.abs(error).mean()),
            "rmse": float(np.sqrt(np.square(error).mean())), "bias": float(error.mean())}


def metric_intervals(frame, prediction, repeats=200, seed=2026):
    """Year-block bootstrap keeps all regions/months in a sampled year together."""
    years = sorted(frame.year.unique())
    if len(years) < 3:
        return {"available": False, "reason": "fewer_than_three_year_blocks"}
    rng, draws = np.random.default_rng(seed), []
    for _ in range(repeats):
        sampled = rng.choice(years, len(years), replace=True)
        indices = np.concatenate([np.flatnonzero(frame.year.to_numpy() == year) for year in sampled])
        draws.append(metrics(frame.activity_reference.to_numpy()[indices], np.asarray(prediction)[indices]))
    return {"available": True, "method": "heldout_year_block_bootstrap_fixed_model",
            "blocks": len(years), "repeats": repeats,
            **{name: np.quantile([d[name] for d in draws], [0.025, 0.975]).tolist()
               for name in ("mae", "rmse", "bias")}}


def trend_metrics(frame, prediction, min_months=6):
    work = frame.assign(prediction=np.asarray(prediction))
    results = []
    for region, data in work.groupby("region_id"):
        years = sorted(data.year.unique())
        if len(years) < 3:
            continue
        common = set.intersection(*(set(data.loc[data.year == y, "month_number"]) for y in years))
        if len(common) < min_months:
            continue
        # Matching calendar-month support prevents changes in sampled season from masquerading as trend.
        annual = data[data.month_number.isin(common)].groupby("year")[[
            "activity_source", "activity_reference", "prediction",
        ]].mean()
        time = annual.index.to_numpy(float)
        time -= time.mean()
        slopes = {key: float(np.linalg.lstsq(np.column_stack([np.ones(len(time)), time]),
                                           annual[key], rcond=None)[0][1]) for key in annual}
        results.append({"region_id": str(region), "years": [int(y) for y in annual.index],
                        "common_months": sorted(int(m) for m in common),
                        "source_slope": slopes["activity_source"],
                        "reference_slope": slopes["activity_reference"],
                        "calibrated_slope": slopes["prediction"],
                        "slope_error": abs(slopes["prediction"] - slopes["activity_reference"]),
                        "baseline_slope_error": abs(slopes["activity_source"] - slopes["activity_reference"]),
                        "change_from_source": slopes["prediction"] - slopes["activity_source"]})
    return {"available": bool(results), "regions": results,
            "mean_slope_error": float(np.mean([r["slope_error"] for r in results])) if results else None,
            "mean_baseline_slope_error": float(np.mean([r["baseline_slope_error"] for r in results])) if results else None,
            "reason": None if results else "insufficient_years_or_common_calendar_months"}


def parameter_intervals(model, train, evaluation, repeats, seed):
    years = sorted(train.year.unique())
    if len(years) < 3 or model["method"] == "baseline":
        return np.full(len(evaluation), np.nan), np.full(len(evaluation), np.nan), 0
    rng, predictions = np.random.default_rng(seed), []
    for _ in range(repeats):
        bootstrap = pd.concat([train[train.year == year] for year in rng.choice(years, len(years))])
        try:
            fitted = fit_model(bootstrap, model["method"], metric=model["metric"], context=model["context"])
            predictions.append(predict_model(fitted, evaluation)[0])
        except ValueError:
            continue
    if len(predictions) < max(20, repeats // 2):
        return np.full(len(evaluation), np.nan), np.full(len(evaluation), np.nan), len(predictions)
    interval = np.quantile(predictions, [0.025, 0.975], axis=0)
    _, extrapolated = predict_model(model, evaluation)
    interval[:, extrapolated] = np.nan
    return interval[0], interval[1], len(predictions)


def evaluate_candidates(pairs: pd.DataFrame, protocol: ValidationProtocol, context=None):
    paired = pairs[pairs.paired].copy().reset_index(drop=True)
    protocol.validate(pairs.region_id.unique())
    if len(paired) == 0:
        raise ValueError("No paired sensor observations; calibration is not estimable")
    if paired[["metric", "coverage_mode"]].drop_duplicates().shape[0] != 1:
        raise ValueError("Do not mix activity metrics or coverage modes")
    holdout = paired.region_id.isin(protocol.heldout_regions)
    labels = np.select([
        paired.year.isin(protocol.train_years) & ~holdout,
        paired.year.isin(protocol.validation_years) & ~holdout,
        paired.year.isin(protocol.test_years) & ~holdout,
        paired.year.isin(protocol.train_years) & holdout,
        paired.year.isin(protocol.test_years) & holdout,
    ], ["train", "validation", "test_years", "test_regions", "test_years_and_regions"], default="excluded")
    paired["split"] = labels
    train = paired[paired.split == "train"]
    if len(train) < protocol.min_training_pairs or train.year.nunique() < 3:
        raise ValueError("Insufficient training overlap: need configured pairs and at least three years")
    metric = paired.metric.iloc[0]
    models, evaluations, predictions = {}, {}, []
    for method in METHODS:
        try:
            model = fit_model(train, method, metric=metric, context=context)
        except ValueError as error:
            evaluations[method] = {"status": "not_estimable", "reason": str(error)}
            continue
        models[method] = model
        estimate, outside = predict_model(model, paired)
        lower, upper, successful = parameter_intervals(
            model, train, paired, protocol.bootstrap_repeats, protocol.seed,
        )
        predictions.append(paired.assign(method=method, model_version=model["model_version"],
                                          prediction=estimate, extrapolated=outside,
                                          parameter_lower_95=lower, parameter_upper_95=upper))
        splits = {}
        for split in ("train", "validation", "test_years", "test_regions", "test_years_and_regions"):
            mask = paired.split == split
            sample = paired.loc[mask]
            splits[split] = {
                **metrics(sample.activity_reference, estimate[mask]),
                "extrapolation_fraction": float(outside[mask].mean()) if mask.any() else None,
                "by_region": {str(region): metrics(group.activity_reference, estimate[group.index])
                              for region, group in sample.groupby("region_id")},
                "by_season": {str(quarter): metrics(group.activity_reference, estimate[group.index])
                              for quarter, group in sample.groupby((sample.month_number - 1) // 3 + 1)},
                "by_reference_product": {str(version): metrics(group.activity_reference, estimate[group.index])
                    for version, group in sample.groupby("product_versions_reference")}
                    if "product_versions_reference" in sample else {},
                "metric_intervals_95": metric_intervals(sample, estimate[mask],
                    protocol.bootstrap_repeats, protocol.seed),
                "trend": trend_metrics(sample, estimate[mask], protocol.min_trend_months),
            }
        evaluations[method] = {"status": "evaluated", "splits": splits,
                               "parameter_bootstrap_successes": successful}
    baseline = evaluations["baseline"]["splits"]
    qualified = []
    for method in ("regression", "quantile_mapping"):
        result = evaluations[method]
        if result["status"] != "evaluated":
            continue
        current, base = result["splits"]["validation"], baseline["validation"]
        failures = []
        if current["n"] < protocol.min_evaluation_pairs:
            failures.append("insufficient_validation_pairs")
        if current["n"]:
            if base["mae"] <= 0 or current["mae"] > base["mae"] * (1 - protocol.min_improvement):
                failures.append("mae_improvement_below_threshold")
            if current["rmse"] > base["rmse"] * (1 - protocol.min_improvement):
                failures.append("rmse_improvement_below_threshold")
            if abs(current["bias"]) > abs(base["bias"]) + 1e-12:
                failures.append("absolute_bias_worsened")
            if current["extrapolation_fraction"] > protocol.max_extrapolation_fraction:
                failures.append("extrapolation_above_threshold")
        result["validation_qualified"] = not failures
        result["validation_rejection_reasons"] = failures
        if not failures:
            qualified.append((current["mae"], method))
    chosen = min(qualified)[1] if qualified else "baseline"
    reasons = []
    if chosen == "baseline":
        reasons.append("no_calibration_passed_validation_selection")
    else:
        for split in ("test_years", "test_regions", "test_years_and_regions"):
            current, base = evaluations[chosen]["splits"][split], baseline[split]
            if current["n"] < protocol.min_evaluation_pairs:
                reasons.append(split + ":insufficient_pairs")
                continue
            if split in ("test_regions", "test_years_and_regions"):
                for region in protocol.heldout_regions:
                    if current["by_region"].get(region, {}).get("n", 0) < protocol.min_evaluation_pairs:
                        reasons.append(split + ":" + region + ":insufficient_region_pairs")
            if (current["mae"] >= base["mae"] or current["rmse"] >= base["rmse"]
                    or abs(current["bias"]) > abs(base["bias"]) + 1e-12):
                reasons.append(split + ":agreement_did_not_improve")
            if current["extrapolation_fraction"] > protocol.max_extrapolation_fraction:
                reasons.append(split + ":excess_extrapolation")
            trend = current["trend"]
            if not trend["available"]:
                reasons.append(split + ":trend_not_estimable")
            elif trend["mean_slope_error"] > trend["mean_baseline_slope_error"] * 1.1 + 1e-12:
                reasons.append(split + ":trend_error_worsened")
    if paired.coverage_mode.iloc[0] != "provided_observability":
        reasons.append("observability_unknown_conditional_detection_comparison_only")
    if metric != "observable_hotspot_cell_day_occupancy":
        reasons.append("metric_is_detection_only_proxy")
    return {
        "protocol": asdict(protocol), "selection_used_test_data": False,
        "selection_rule": "minimum validation MAE among predeclared qualifying candidates; tests never choose a replacement",
        "validation_selected_method": chosen, "operational_calibration_supported": not reasons,
        "operational_method": chosen if not reasons else "baseline",
        "limitations_or_rejection_reasons": reasons, "evaluations": evaluations,
        "unpaired_bins": int((~pairs.paired).sum()), "paired_bins": len(paired),
        "metric": metric, "models": models,
    }, pd.concat(predictions, ignore_index=True)
