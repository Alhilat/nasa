"""Synthetic counts test mathematics only, never served as observations."""

import copy

import pytest
from app.calendar_statistics import median_comparisons


def row(month, value, **extra):
    return {"month": month, "value": value, "completeness": "complete", **extra}


def compare(rows, **extra):
    return median_comparisons(
        rows, **{"baseline_start_year": 2013, "baseline_end_year": 2020, "min_years": 3, **extra}
    )


def test_signed_departures_use_only_complete_earlier_same_month_years():
    rows = [
        row("2013-01", 10),
        row("2014-01", 20),
        row("2015-01", 30),
        row("2016-01", 50),
        row("2015-02", 10000),
        row("2017-01", 100000),
    ]
    original = copy.deepcopy(rows)
    result = compare(rows)["2016-01"]
    assert result["historical_median"] == 20
    assert result["departure"] == 30
    assert result["departure_percent"] == 150
    assert result["baseline_years"] == [2013, 2014, 2015]
    assert result["status"] == "assessed"
    assert rows == original
    assert compare(list(reversed(rows)))["2016-01"] == result


def test_requested_baseline_interval_is_respected_without_lookahead():
    rows = [
        row(f"{y}-07", n)
        for y, n in [(2013, 1000), (2014, 5), (2015, 10), (2016, 15), (2017, 5), (2018, 100000)]
    ]
    result = compare(rows, baseline_start_year=2014, baseline_end_year=2016)["2017-07"]
    assert result["baseline_years"] == [2014, 2015, 2016]
    assert result["departure"] == -5
    assert result["departure_percent"] == -50


def test_zero_median_has_finite_absolute_departure_and_unknown_percentage():
    rows = [row(f"{y}-01", 0) for y in (2013, 2014, 2015)] + [row("2016-01", 5)]
    result = compare(rows)["2016-01"]
    assert result["departure"] == 5
    assert result["departure_percent"] is None
    assert "zero" in result["reason"]


@pytest.mark.parametrize(
    "exclusion", ["unapproved_mapping", "extrapolated", "unsupported_processing"]
)
def test_excluded_values_never_enter_baselines_or_receive_assessed_colors(exclusion):
    rows = [
        row("2013-01", 10),
        row("2014-01", 20),
        row("2015-01", 1000, exclusion_reason=exclusion),
        row("2016-01", 30),
        row("2017-01", 40, exclusion_reason=exclusion),
    ]
    result = compare(rows)
    assert result["2016-01"]["baseline_size"] == 2
    assert result["2016-01"]["departure"] is None
    assert result["2017-01"]["status"] == exclusion
    assert result["2017-01"]["departure"] is None


def test_unknown_completeness_missing_values_and_short_history_stay_unassessed():
    rows = [
        row("2013-01", 1),
        row("2014-01", 2, completeness="unknown"),
        row("2015-01", None),
        row("2016-01", 3),
    ]
    result = compare(rows)
    assert result["2014-01"]["status"] == "incomplete_archive"
    assert result["2015-01"]["status"] == "missing_value"
    assert result["2016-01"]["status"] == "insufficient_history"
    assert result["2016-01"]["baseline_years"] == [2013]
    assert all(r["departure"] is None for r in result.values())


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_numeric_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        compare([row("2013-01", value)])


def test_duplicate_months_and_invalid_reference_configuration_are_rejected():
    with pytest.raises(ValueError):
        compare([row("2013-01", 1), row("2013-01", 2)])
    with pytest.raises(ValueError):
        compare([], min_years=2)
    with pytest.raises(ValueError):
        compare([], baseline_end_year=2012)
