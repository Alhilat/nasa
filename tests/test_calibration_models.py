"""Explicitly synthetic statistical test functions, not fire measurements."""
import copy

import numpy as np
import pandas as pd
import pytest

from firescope_pipeline.calibration.models import fit_model, predict_model
from firescope_pipeline.calibration.validation import (
    ValidationProtocol, evaluate_candidates, metrics, metric_intervals,
    seasonal_metrics, trend_metrics,
)


def synthetic_pairs():
    rows = []
    for year in range(2013, 2026):
        for region_number, region in enumerate(("a", "b", "c")):
            for month in range(1, 13):
                x = .4 + .12 * np.sin(month / 2) + .03 * np.cos(year) + .003 * region_number
                y = np.expm1(.03 + .8 * np.log1p(x) + .01 * np.sin(2 * np.pi * (month - 1) / 12))
                rows.append({"region_id": region, "month": f"{year}-{month:02}", "year": year,
                             "month_number": month, "activity_source": x, "activity_reference": y,
                             "paired": True, "metric": "observable_hotspot_cell_day_occupancy",
                             "coverage_mode": "provided_observability"})
    return pd.DataFrame(rows)


def protocol():
    return ValidationProtocol(tuple(range(2013, 2020)), (2020, 2021), tuple(range(2022, 2026)),
                              ("c",), bootstrap_repeats=20, max_extrapolation_fraction=.3)


def test_regression_recovers_known_seasonal_function_and_serializes_without_nan():
    data = synthetic_pairs()
    model = fit_model(data[data.year <= 2019], "regression", metric=data.metric.iloc[0])
    estimate, outside = predict_model(model, data[data.year >= 2022])
    assert np.max(np.abs(estimate - data.loc[data.year >= 2022, "activity_reference"])) < 1e-10
    assert len(model["model_version"]) == 64
    assert np.isfinite(estimate).all()


def test_quantile_mapping_is_monotonic_with_ties_and_flags_tails():
    data = synthetic_pairs()
    data["activity_source"] = np.round(data.activity_source, 2)
    model = fit_model(data, "quantile_mapping", metric=data.metric.iloc[0])
    query = data.iloc[:20].copy()
    query["activity_source"] = np.linspace(0, 2, len(query))
    query["month_number"] = 1
    prediction, outside = predict_model(model, query)
    assert np.diff(prediction).min() >= -1e-12
    assert outside[0] and outside[-1]
    assert prediction[-1] == prediction[-2]  # Explicit clipping of unobserved tail.


def test_missing_input_stays_missing_and_no_negative_activity_is_returned():
    data = synthetic_pairs()
    for method in ("baseline", "regression", "quantile_mapping"):
        model = fit_model(data, method, metric=data.metric.iloc[0])
        query = data.iloc[:3].copy()
        query.loc[query.index[0], "activity_source"] = np.nan
        query.loc[query.index[1], "activity_source"] = -1
        prediction, _ = predict_model(model, query)
        assert np.isnan(prediction[0]) and np.isnan(prediction[1])
        assert prediction[2] >= 0


def test_heldout_years_and_regions_never_change_fitted_models_or_selection():
    data = synthetic_pairs()
    report, predictions = evaluate_candidates(data, protocol())
    changed = data.copy()
    changed.loc[(changed.year >= 2022) | (changed.region_id == "c"), "activity_reference"] += .1
    modified, _ = evaluate_candidates(changed, protocol())
    assert report["models"] == modified["models"]
    assert report["validation_selected_method"] == modified["validation_selected_method"]
    for model in report["models"].values():
        assert "c" not in model["training_regions"]
        assert max(model["training_years"]) == 2019
    assert not report["selection_used_test_data"]
    assert set(predictions[predictions.split == "train"].region_id) == {"a", "b"}


def test_detection_only_comparison_can_never_be_marked_operational():
    data = synthetic_pairs()
    data["coverage_mode"] = "detection_only_conditional"
    report, _ = evaluate_candidates(data, protocol())
    assert not report["operational_calibration_supported"]
    assert report["operational_method"] == "baseline"
    assert "observability_unknown_conditional_detection_comparison_only" in report["limitations_or_rejection_reasons"]


def test_metrics_sign_missingness_and_clustered_uncertainty():
    result = metrics([1, 2, np.nan], [2, 4, 7])
    assert result == {"n": 2, "mae": 1.5, "rmse": np.sqrt(2.5), "bias": 1.5}
    data = synthetic_pairs()
    interval = metric_intervals(data, data.activity_source, repeats=20)
    assert interval["available"] and interval["blocks"] == 13
    assert interval == metric_intervals(data, data.activity_source, repeats=20)
    assert not metric_intervals(data[data.year == 2020], data.loc[data.year == 2020, "activity_source"])["available"]


def test_trend_requires_common_seasonal_support_and_reports_slope_distortion():
    data = synthetic_pairs()
    full = trend_metrics(data, data.activity_reference)
    assert full["available"] and full["mean_slope_error"] == pytest.approx(0)
    partial = data[data.month_number == 1]
    assert not trend_metrics(partial, partial.activity_source)["available"]


def test_seasonal_profile_detects_distortion_and_requires_complete_years():
    data = synthetic_pairs()
    perfect = seasonal_metrics(data, data.activity_reference)
    assert perfect["available"] and perfect["profile_mae"] == pytest.approx(0)
    distorted = data.activity_reference + np.where(data.month_number <= 3, .2, 0)
    assert seasonal_metrics(data, distorted)["profile_mae"] > 0
    partial = data[data.month_number <= 6]
    assert not seasonal_metrics(partial, partial.activity_reference)["available"]


def test_operational_gate_rejects_worsened_seasonal_profile(monkeypatch):
    monkeypatch.setattr("firescope_pipeline.calibration.validation.seasonal_metrics",
                        lambda *_: {"available": True, "profile_mae": 2.,
                                    "baseline_profile_mae": 1.})
    report, _ = evaluate_candidates(synthetic_pairs(), protocol())
    assert not report["operational_calibration_supported"]
    assert ("test_years:seasonal_profile_error_worsened"
            in report["limitations_or_rejection_reasons"])


def test_overlapping_time_splits_are_rejected():
    invalid = ValidationProtocol((2013, 2014), (2014, 2015), (2016,), ("c",), bootstrap_repeats=20)
    with pytest.raises(ValueError, match="disjoint"):
        invalid.validate(["a", "b", "c"])


def test_model_versions_change_with_training_values_and_missing_variation_is_rejected():
    data = synthetic_pairs()
    first = fit_model(data, "regression", metric=data.metric.iloc[0])
    changed = data.copy()
    changed.loc[0, "activity_reference"] += .1
    second = fit_model(changed, "regression", metric=data.metric.iloc[0])
    assert first["model_version"] != second["model_version"]
    data["activity_source"] = 1
    with pytest.raises(ValueError, match="distinct"):
        fit_model(data, "regression", metric=data.metric.iloc[0])


def test_sufficient_synthetic_exposure_and_holdouts_can_pass_without_automatic_real_data_approval():
    report, _ = evaluate_candidates(synthetic_pairs(), protocol())
    assert report["validation_selected_method"] == "regression"
    assert report["operational_calibration_supported"]
    assert not report["limitations_or_rejection_reasons"]


def test_real_proxy_can_never_pass_even_if_coverage_label_is_incorrectly_set():
    data = synthetic_pairs()
    data["metric"] = "reported_cell_days_per_1000km2_month"
    report, _ = evaluate_candidates(data, protocol())
    assert not report["operational_calibration_supported"]
    assert "metric_is_detection_only_proxy" in report["limitations_or_rejection_reasons"]
