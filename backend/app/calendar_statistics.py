"""Pure same-month historical median comparisons, with no I/O or inferred observations."""

import math
from statistics import median


def median_comparisons(rows, *, baseline_start_year, baseline_end_year, min_years):
    """Return descriptive signed departures; only complete, eligible earlier years qualify.

    Rows belong to one sensor/scale and carry month, value, completeness, plus an
    optional exclusion_reason. Percent departure is unknown when the median is zero.
    """
    if baseline_start_year > baseline_end_year or min_years < 3:
        raise ValueError("Use an ordered baseline interval and at least three reference years")
    if len({row["month"] for row in rows}) != len(rows):
        raise ValueError("Monthly values must be unique within one sensor/reference scale")
    for row in rows:
        value = row["value"]
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Calendar values must be finite and nonnegative, or null")
    output = {}
    for row in rows:
        year, month = int(row["month"][:4]), row["month"][5:]
        reference = sorted(
            (
                r
                for r in rows
                if r["month"][5:] == month
                and baseline_start_year <= int(r["month"][:4]) <= baseline_end_year
                and int(r["month"][:4]) < year
                and r["value"] is not None
                and r["completeness"] == "complete"
                and not r.get("exclusion_reason")
            ),
            key=lambda r: r["month"],
        )
        years = [int(r["month"][:4]) for r in reference]
        center = float(median(r["value"] for r in reference)) if len(years) >= min_years else None
        status = (
            "missing_value"
            if row["value"] is None
            else row.get("exclusion_reason")
            or (
                "incomplete_archive"
                if row["completeness"] != "complete"
                else "insufficient_history"
                if center is None
                else "assessed"
            )
        )
        difference = row["value"] - center if status == "assessed" else None
        percent = 100 * difference / center if difference is not None and center else None
        reason = {
            "missing_value": "No month value is available; missing is not zero.",
            "incomplete_archive": "Archive completeness unknown; median departure is unassessed.",
            "insufficient_history": f"Only {len(years)} complete earlier same-month years; "
            f"{min_years} required.",
            "unapproved_mapping": "Experimental mapped values cannot supply a historical baseline "
            "or assessed median departure.",
            "extrapolated": "Outside calibration support; no median departure is assessed.",
            "unsupported_processing": "NRT or mixed processing is excluded from median baselines.",
            "assessed": f"Compared with {len(years)} complete earlier instances of this calendar "
            "month in the requested baseline interval. Descriptive, not fire risk.",
        }[status]
        if status == "assessed" and center == 0:
            reason += " Historical median is zero; percentage departure is undefined."
        output[row["month"]] = {
            "historical_median": center,
            "departure": difference,
            "departure_percent": percent,
            "baseline_size": len(years),
            "baseline_years": years,
            "status": status,
            "reason": reason,
        }
    return output
