"""Pure retrospective MODIS-scale calendar. No database, filesystem or network access.

Reuse the calibration engine with the monthly-count metric, never its grid-density
artifacts. An on-selection fit is always experimental, even with good agreement.
"""

import numpy as np
import pandas as pd
from firescope_pipeline.calibration.models import fit_model, predict_model
from firescope_pipeline.calibration.validation import metrics, parameter_intervals

from app.calendar_schemas import HarmonizedCalendar
from app.calendar_statistics import median_comparisons

VERSION = "modis-calendar-v2"
METRIC = "monthly_normalized_detection_count"
METHODS = ("regression", "quantile_mapping")
REPEATS = 100
SEED = 2026
LIMITATIONS = [
    "MODIS-equivalent thermal detections are not unique fires, burned area or fire risk.",
    "Experimental fits describe the selected archive retrospectively; they are not approved "
    "for operational use and do not establish physical fire truth or satellite exposure.",
    "Unknown-completeness positive counts are conditional archive observations. Missing bins "
    "stay null; only complete archive months can contribute observed zero counts.",
    "95% year-block bootstrap bands describe fitted-parameter uncertainty only, not "
    "prediction intervals, sensor detection error or uncertainty in missing observations.",
    "No band is reported outside training support or for native MODIS reference values.",
]


def _finite(value):
    return round(float(value), 6) if value is not None and np.isfinite(value) else None


def usable_calendar_month(row, sources):
    if not row or row["count"] is None:
        return False
    if row["count"] == 0 and row["completeness"] != "complete":
        return False
    if row.get("missing_data_status") in {
        "pre_operational_sensor",
        "sensor_transition_partial_month",
        "nrt_unreconciled",
        "mixed_processing_revisions",
        "partial_month_archive",
        "spatial_scope_mismatch",
    }:
        return False
    ids = set(row.get("source_ids", [])) | set(row.get("completeness_source_ids", []))
    # An explicit complete-month declaration can attest an empty archive bin.
    if not ids:
        return row["completeness"] == "complete"
    return all(sid in sources and sources[sid].get("processing_level") == "standard" for sid in ids)


def build_calendar(
    monthly,
    sources,
    sensors,
    *,
    approved_models=(),
    scope=None,
    baseline_start_year=None,
    baseline_end_year=None,
    min_baseline_years=5,
):
    """Prefer one fixed MODIS reference, then one mapped VIIRS sensor; never sum sensors.

    Registered models must already pass the history metric/scope/version/approval checks.
    Otherwise fit both existing methods to paired standard-product archive counts. Choose
    by MAE on the latest overlap year, then refit on the overlap for retrospective use.
    """
    source_index = {s["id"]: s for s in sources}
    index = {(r["sensor_code"], r["month"]): r for r in monthly}
    labels = sorted({r["month"] for r in monthly})
    usable = {key: row for key, row in index.items() if usable_calendar_month(row, source_index)}
    references = [s for s in ("MODIS_AQUA", "MODIS_TERRA") if s in sensors]
    viirs = [s for s in ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21") if s in sensors]
    # Choose an approved pair first, otherwise the pair with most usable overlap.
    approved = sorted(
        [
            m
            for m in approved_models
            if m["artifact"]["context"]["reference"] in references
            and m["artifact"]["context"]["source"] in viirs
        ],
        key=lambda m: (m["method"], m["model_version"]),
    )

    def overlap(ref, src):
        return sum((ref, m) in usable and (src, m) in usable for m in labels)

    def ref_coverage(ref):
        return sum((ref, m) in usable for m in labels)

    if approved:
        context = approved[0]["artifact"]["context"]
        reference, source = context["reference"], context["source"]
    elif references and viirs:
        reference, source = max(
            ((ref, src) for ref in references for src in viirs),
            key=lambda pair: (
                overlap(*pair),
                ref_coverage(pair[0]),
                -references.index(pair[0]),
                -viirs.index(pair[1]),
            ),
        )
    else:
        reference = (
            max(references, key=lambda ref: (ref_coverage(ref), -references.index(ref)))
            if references
            else None
        )
        source = next(iter(viirs), None)

    pairs = pd.DataFrame(
        [
            {
                "region_id": "selection",
                "month": m,
                "year": int(m[:4]),
                "month_number": int(m[5:]),
                "activity_source": usable[source, m]["count"],
                "activity_reference": usable[reference, m]["count"],
            }
            for m in labels
            if (reference, m) in usable and (source, m) in usable
        ],
        columns=[
            "region_id",
            "month",
            "year",
            "month_number",
            "activity_source",
            "activity_reference",
        ],
    )
    model, model_info, candidates = None, None, []
    train = pairs
    if approved:
        model = approved[0]["artifact"]
        model_info = {
            "method": model["method"],
            "model_version": model["model_version"],
            "artifact": model,
            "approval": "supported_for_scope",
            "training_months": [],
            "selection_year": None,
            "selection_mae": None,
            "bootstrap_successes": 0,
        }
    elif not pairs.empty:
        years = sorted(int(y) for y in pairs.year.unique())
        # A recent partial year must not disable a fit supported by older overlap.
        eligible_years = [year for year in years if len(pairs[pairs.year == year]) >= 8]
        selection_year = eligible_years[-1] if eligible_years else years[-1]
        fit_pairs = pairs[pairs.year < selection_year]
        selection = pairs[pairs.year == selection_year]
        enough = len(fit_pairs) >= 24 and fit_pairs.year.nunique() >= 3 and len(selection) >= 8
        fits = []
        context = {
            "source": source,
            "reference": reference,
            "daynight": "all",
            "history_scope": scope or {},
            "calendar_version": VERSION,
            "coverage_mode": "conditional_archive_counts",
        }
        for method in METHODS:
            reason = "Need 24 earlier pairs across 3 years and 8 latest-year selection pairs."
            error = None
            if enough:
                try:
                    candidate = fit_model(fit_pairs, method, metric=METRIC, context=context)
                    prediction, _ = predict_model(candidate, selection)
                    error = metrics(selection.activity_reference, prediction)["mae"]
                    fits.append((error, method))
                except ValueError as exc:
                    reason = str(exc)
            candidates.append(
                {
                    "method": method,
                    "available": error is not None,
                    "validation_mae": error,
                    "reason": None if error is not None else reason,
                }
            )
        if fits:
            error, method = min(fits)
            model = fit_model(pairs, method, metric=METRIC, context=context)
            model_info = {
                "method": method,
                "model_version": model["model_version"],
                "artifact": model,
                "approval": "experimental",
                "training_months": pairs.month.tolist(),
                "selection_year": selection_year,
                "selection_mae": error,
                "bootstrap_successes": 0,
            }

    evaluation = pd.DataFrame(
        [
            {"month": m, "month_number": int(m[5:]), "activity_source": usable[source, m]["count"]}
            for m in labels
            if (source, m) in usable
        ],
        columns=["month", "month_number", "activity_source"],
    )
    mapped = {}
    if model is not None and not evaluation.empty:
        prediction, outside = predict_model(model, evaluation)
        lower, upper = np.full(len(evaluation), np.nan), np.full(len(evaluation), np.nan)
        # A registered model's actual training rows are not available here. Refitting
        # the current overlap would describe a different model's uncertainty.
        if model_info["approval"] == "experimental":
            lower, upper, successes = parameter_intervals(model, train, evaluation, REPEATS, SEED)
            model_info["bootstrap_successes"] = successes
        for i, m in enumerate(evaluation.month):
            mapped[m] = (
                _finite(prediction[i]),
                _finite(lower[i]),
                _finite(upper[i]),
                bool(outside[i]),
            )

    rows = []
    for m in labels:
        ref_row, src_row = usable.get((reference, m)), usable.get((source, m))
        # Complete source estimates can fill an incomplete reference archive month.
        use_reference = ref_row is not None and (
            ref_row["completeness"] == "complete"
            or m not in mapped
            or src_row["completeness"] != "complete"
        )
        m_val, m_lo, m_hi, m_out = mapped[m] if m in mapped else (None, None, None, None)
        value, lo, hi, outside = None, None, None, False
        origin, native, status = "missing", None, "unavailable"
        reason = "No usable standard-product reference or calibrated source month."
        uncertainty = "No estimate available."
        if use_reference:
            native, origin, value = ref_row, "modis_reference", float(ref_row["count"])
            status = "experimental"
            reason = "Native MODIS reference; no cross-sensor estimate or pooling."
            uncertainty = "Native MODIS reference; observation uncertainty is not quantified."
        elif m in mapped:
            native, origin = src_row, "mapped_viirs"
            value, lo, hi, outside = mapped[m]
            status = (
                "validated"
                if model_info["approval"] == "supported_for_scope"
                and native["completeness"] == "complete"
                and not outside
                else "experimental"
            )
            reason = "VIIRS mapped to the fixed MODIS reference with " + model["method"] + "."
            if lo is not None:
                uncertainty = "95% year-block bootstrap fitted-parameter interval."
            elif outside:
                uncertainty = "Outside training support; band withheld."
            elif model_info["approval"] == "supported_for_scope":
                uncertainty = "Actual registered training rows unavailable; band unknown."
            else:
                uncertainty = "Insufficient successful year-block bootstrap fits; band unknown."
        if native and native["completeness"] != "complete":
            reason += " Archive completeness unknown; conditional observed-count comparison only."
        if outside:
            reason += " Outside training support; quantile clipping or regression extrapolation."
        rows.append(
            {
                "month": m,
                "value": value,
                "lower_95": lo,
                "upper_95": hi,
                "mapped_value": m_val,
                "mapped_lower_95": m_lo,
                "mapped_upper_95": m_hi,
                "mapped_extrapolated": m_out,
                "sensor_code": native["sensor_code"] if native else None,
                "origin": origin,
                "validation_status": status,
                "completeness": native["completeness"] if native else "unknown",
                "extrapolated": outside,
                "model_version": model["model_version"] if origin == "mapped_viirs" else None,
                "source_ids": sorted(
                    set(native.get("source_ids", []))
                    | set(native.get("completeness_source_ids", []))
                )
                if native
                else [],
                "reason": reason,
                "uncertainty_reason": uncertainty,
            }
        )
    if rows:
        context_rows = [
            {
                **r,
                "exclusion_reason": "extrapolated"
                if r["extrapolated"]
                else "unapproved_mapping"
                if r["origin"] == "mapped_viirs" and r["validation_status"] != "validated"
                else None,
            }
            for r in rows
        ]
        comparisons = median_comparisons(
            context_rows,
            baseline_start_year=baseline_start_year
            if baseline_start_year is not None
            else int(labels[0][:4]),
            baseline_end_year=baseline_end_year
            if baseline_end_year is not None
            else int(labels[-1][:4]),
            min_years=min_baseline_years,
        )
        for row in rows:
            row["median_comparison"] = comparisons[row["month"]]
    status = "experimental" if any(r["value"] is not None for r in rows) else "unavailable"
    if status != "unavailable" and model_info and model_info["approval"] == "supported_for_scope":
        status = (
            "validated"
            if not any(
                r["validation_status"] == "experimental"
                if r["origin"] == "mapped_viirs"
                else r["completeness"] != "complete"
                for r in rows
                if r["value"] is not None
            )
            else "experimental"
        )
    if approved:
        reason = (
            "Approved scope-specific calibration; extrapolated or incomplete months "
            "remain experimental."
        )
    elif model:
        reason = "Retrospective archive calibration is experimental."
    else:
        reason = (
            "No estimable compatible calibration; only available native MODIS reference "
            "months are shown. Select MODIS and VIIRS with sufficient overlap."
        )
    return HarmonizedCalendar(
        algorithm_version=VERSION,
        status=status,
        reference_sensor=reference,
        source_sensor=source,
        units=f"{reference or 'MODIS'}-equivalent detections per month",
        selection_policy="One fixed MODIS reference and VIIRS source; prefer complete MODIS, "
        "then complete mapped VIIRS, then observed MODIS, then observed mapped VIIRS. Never sum.",
        uncertainty_method=f"95% parameter year-block bootstrap; {REPEATS} repeats; seed {SEED}.",
        reason=reason,
        limitations=LIMITATIONS,
        candidates=candidates,
        model=model_info,
        monthly=rows,
    ).model_dump(mode="json")
