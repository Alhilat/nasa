import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from firescope_pipeline.calibration.activity import aggregate_activity, pair_sensors
from firescope_pipeline.calibration.io import code_hash, read_study, write_json
from firescope_pipeline.calibration.models import fingerprint
from firescope_pipeline.calibration.plots import comparison_charts
from firescope_pipeline.calibration.validation import ValidationProtocol, evaluate_candidates


def run_study(manifest_path, regions_path, protocol_path, output_path, *, exposure_path=None):
    output = Path(output_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be new or empty; model versions are never overwritten")
    config = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    observations, provenance = read_study(manifest_path)
    regions = gpd.read_file(regions_path)
    protocol = ValidationProtocol(**{**config["validation"],
        **{name: tuple(config["validation"][name]) for name in (
            "train_years", "validation_years", "test_years", "heldout_regions")}})
    source, reference = config.get("source", "VIIRS_SNPP"), config.get("reference", "MODIS_AQUA")
    exposure = pd.read_csv(exposure_path) if exposure_path else None
    activity = aggregate_activity(
        observations, regions, start=config["start"], end=config["end"],
        grid_size_m=config.get("grid_size_m", 5000), exposure=exposure,
        paired_sensors=(source, reference), min_coverage=config.get("min_coverage", 0.8),
    )
    pairs = pair_sensors(activity.monthly, source, reference, config.get("daynight", "D"))
    months = pd.date_range(pd.Timestamp(config["start"]).tz_convert("UTC"),
                           pd.Timestamp(config["end"]).tz_convert("UTC"), freq="MS", inclusive="left")
    calendar = pd.MultiIndex.from_product([
        sorted(activity.audit["region_areas_km2"]), months.strftime("%Y-%m")],
        names=["region_id", "month"]).to_frame(index=False)
    pairs = calendar.merge(pairs, on=["region_id", "month"], how="left")
    pairs["paired"] = pairs.paired.eq(True)
    pairs["year"] = pairs.month.str[:4].astype(int)
    pairs["month_number"] = pairs.month.str[5:7].astype(int)
    pairs["metric"] = activity.monthly.metric.iloc[0]
    pairs["coverage_mode"] = activity.audit["coverage_mode"]
    native_versions = {}
    for sensor, data in observations.groupby("sensor_code"):
        native_versions[str(sensor)] = sorted(str(v) for v in data.product_version.unique())
    mixed = any(len(versions) > 1 for sensor, versions in native_versions.items() if sensor in (source, reference))
    if mixed and not config.get("allow_product_transition_evaluation", False):
        raise ValueError("Mixed native product versions: stratify inputs or explicitly request transition evaluation")
    context = {"source": source, "reference": reference, "daynight": config.get("daynight", "D"),
               "native_product_versions": native_versions, "code_sha256": code_hash(),
               "grid_size_m": config.get("grid_size_m", 5000),
               "region_geometry_sha256": hashlib.sha256(Path(regions_path).read_bytes()).hexdigest()}
    evaluation, predictions = evaluate_candidates(pairs, protocol, context)
    if mixed:
        evaluation["limitations_or_rejection_reasons"].append("native_product_transition_evaluation_only")
        evaluation["operational_calibration_supported"] = False
        evaluation["operational_method"] = "baseline"
    evaluation["interpretation"] = "Agreement to a sensor reference, not validation against physical fire truth"
    evaluation["both_sensors_missing_bins"] = int((pairs.activity_source.isna() & pairs.activity_reference.isna()).sum())
    evaluation["source_sensor"], evaluation["reference_sensor"] = source, reference
    evaluation["daynight"] = config.get("daynight", "D")
    evaluation["native_product_versions"] = native_versions
    study_id = fingerprint({"config": config, "provenance": provenance, "context": context,
                            "exposure_sha256": hashlib.sha256(Path(exposure_path).read_bytes()).hexdigest()
                            if exposure_path else None})
    output.mkdir(parents=True, exist_ok=True)
    observations.assign(acquired_at=observations.acquired_at.astype(str)).to_csv(output / "sensor-observations.csv", index=False)
    activity.monthly.to_csv(output / "sensor-monthly.csv", index=False)
    activity.cells.drop(columns="geometry").to_csv(output / "grid-cells.csv", index=False)
    pairs.to_csv(output / "all-pairs-including-missing.csv", index=False)
    predictions.to_csv(output / "candidate-predictions.csv", index=False)
    write_json(output / "evaluation.json", evaluation)
    write_json(output / "protocol.json", config)
    for method, model in evaluation["models"].items():
        write_json(output / f"model-{method}.json", model)
    comparison_charts(predictions, evaluation, output)
    _write_report(output, evaluation, activity.audit, provenance)
    import importlib.metadata
    manifest = {"study_id": study_id, "input_provenance": provenance,
                "activity_audit": activity.audit, "code_sha256": context["code_sha256"],
                "dependency_versions": {name: importlib.metadata.version(name)
                    for name in ("numpy", "pandas", "geopandas", "shapely", "pyproj", "matplotlib")},
                "region_geometry_sha256": context["region_geometry_sha256"],
                "exposure_manifest_provided": exposure_path is not None,
                "artifacts": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(output.iterdir()) if p.is_file()}}
    write_json(output / "manifest.json", manifest)
    return {"study_id": study_id, "output": str(output.resolve()),
            "paired_bins": evaluation["paired_bins"], "unpaired_bins": evaluation["unpaired_bins"],
            "validation_selected_method": evaluation["validation_selected_method"],
            "operational_calibration_supported": evaluation["operational_calibration_supported"],
            "limitations_or_rejection_reasons": evaluation["limitations_or_rejection_reasons"]}


def _write_report(output, evaluation, audit, provenance):
    lines = ["# FireScope sensor harmonization: measured overlap results", "",
             "This report compares satellite-derived activity, not unique fires or burned area.", "",
             f"Coverage mode: **{audit['coverage_mode']}**. Missing bins were not filled with zero.",
             f"Reference: {evaluation['reference_sensor']}; source: {evaluation['source_sensor']}; paired bins: {evaluation['paired_bins']}; unpaired calendar bins: {evaluation['unpaired_bins']} (both missing: {evaluation['both_sensors_missing_bins']}).",
             f"Spatial grid: {audit['grid_size_m']} m, EPSG:6933; boundary cells excluded: {audit['shared_boundary_cells_excluded']}.",
             f"Validation-selected method: **{evaluation['validation_selected_method']}**.",
             f"Operational calibration supported: **{evaluation['operational_calibration_supported']}**.", "",
             "## Held-out temporal results", "",
             "| Method | Paired bins | MAE | RMSE | Bias (estimate − reference) | Extrapolated fraction |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for method, result in evaluation["evaluations"].items():
        if result["status"] != "evaluated":
            lines.append(f"| {method} | not estimable | — | — | — | — |")
            continue
        score = result["splits"]["test_years"]
        values = [str(score["n"])] + [f"{score[k]:.6g}" if score[k] is not None else "not estimable"
                                    for k in ("mae", "rmse", "bias", "extrapolation_fraction")]
        lines.append("| " + method + " | " + " | ".join(values) + " |")
    lines += ["", "## Validation limits", ""]
    lines += ["- " + reason for reason in evaluation["limitations_or_rejection_reasons"]]
    lines += ["", "## All blocked test scenarios", "",
              "| Method | Scenario | Pairs | Trend estimable |", "| --- | --- | ---: | --- |"]
    for method, result in evaluation["evaluations"].items():
        if result["status"] != "evaluated":
            continue
        for split in ("test_years", "test_regions", "test_years_and_regions"):
            score = result["splits"][split]
            lines.append(f"| {method} | {split} | {score['n']} | {score['trend']['available']} |")
    lines += ["", "The method was selected using validation data only. Test years and held-out regions were not used in fitting or selection.",
              "Year-block bootstrap intervals quantify finite-sample agreement/parameter variability only, not physical detection uncertainty.",
              "Native versions are retained below; numeric labels are not silently translated into collection identifiers.",
              "", "```json", json.dumps(evaluation["native_product_versions"], indent=2), "```", "",
              "## Figures", "", "![Before and after comparison](before-after.png)", "",
              "![Held-out metrics](heldout-metrics.png)", "", "![Overlap series](overlap-series.png)", "",
              "## Provenance", "", f"{len(provenance)} hash-verified original CSV files; see manifest.json.",
              "sensor-observations.csv preserves normalized input sensor records and source hashes; source CSV bytes remain in the original archive.",
              "sensor-monthly.csv retains individual sensors and strata; all-pairs-including-missing.csv retains unpaired bins.",
              "candidate-predictions.csv contains statistical estimates separately from observations."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
