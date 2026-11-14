"""Exportable scientific figures; all points are measured activities or labeled estimates."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS = {"baseline": "#66758c", "regression": "#e47837", "quantile_mapping": "#5c8c6b"}


def comparison_charts(predictions, evaluation, output):
    output = Path(output)
    methods = list(evaluation["models"])
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "svg.hashsalt": "firescope-sensor-calibration-v1",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": "white", "axes.facecolor": "#fafbfc"})
    heldout = predictions[predictions.split.isin(["test_years", "test_years_and_regions"])]
    if heldout.empty:
        heldout = predictions[predictions.split == "validation"]
        scope = "Validation years (test years unavailable)"
    else:
        scope = "Held-out years"
    figure, axes = plt.subplots(1, len(methods), figsize=(5 * len(methods), 5), squeeze=False,
                                sharex=True, sharey=True)
    common_max = max(float(heldout.activity_reference.max()), float(heldout.prediction.max()), 1e-6) if len(heldout) else 1
    for axis, method in zip(axes[0], methods):
        data = heldout[heldout.method == method]
        axis.scatter(data.activity_reference, data.prediction, s=27, alpha=0.75,
                     color=COLORS[method], edgecolors="white", linewidths=0.4)
        axis.plot([0, common_max], [0, common_max], "--", color="#a5abb2", lw=1)
        axis.set_xlim(-.03 * common_max, 1.03 * common_max)
        axis.set_ylim(-.03 * common_max, 1.03 * common_max)
        axis.set(xlabel="Reference activity", ylabel="Source / estimated activity" if method == methods[0] else "",
                 title=f"{method.replace('_', ' ').title()} · n={len(data)}")
        axis.grid(alpha=0.2)
    figure.suptitle(evaluation["source_sensor"] + " → " + evaluation["reference_sensor"]
                     + " · " + scope + " · common axes", fontsize=14, y=1.04)
    figure.text(0.5, -0.04, "Cross-sensor statistical estimates, not fire events or burned area. See scope/validation limits in the report.",
                ha="center", fontsize=9, color="#687481")
    figure.tight_layout()
    figure.savefig(output / "before-after.png", dpi=180, bbox_inches="tight")
    figure.savefig(output / "before-after.svg", bbox_inches="tight", metadata={"Date": None, "Creator": "FireScope"})
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    data = heldout[heldout.method == "baseline"]
    axes[0].scatter(data.raw_detection_count_reference, data.raw_detection_count_source, s=24,
                    color="#66758c", alpha=.7)
    axes[0].set(xlabel="MODIS native detections", ylabel="VIIRS native detections",
                title="Before: native hotspot counts")
    axes[1].scatter(data.activity_reference, data.activity_source, s=24, color="#e47837", alpha=.7)
    axes[1].set(xlabel="MODIS common activity", ylabel="VIIRS common activity",
                title="After baseline spatial/time aggregation")
    figure.suptitle("Held-out bins · counts are detections, not unique fire events", fontsize=12)
    for axis in axes:
        axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(output / "counts-to-common-activity.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    figure, axes = plt.subplots(1, 3, figsize=(13, 4))
    for axis, metric in zip(axes, ("mae", "rmse", "bias")):
        values, labels = [], []
        for method in methods:
            result = evaluation["evaluations"][method]["splits"]["test_years"]
            values.append(result[metric] if result[metric] is not None else np.nan)
            labels.append(method.replace("_", "\n"))
        axis.bar(labels, values, color=[COLORS[m] for m in methods], width=0.55)
        axis.axhline(0, color="#87909a", lw=0.7)
        axis.set_title(metric.upper())
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle("Held-out temporal agreement with MODIS reference", fontsize=14)
    figure.tight_layout()
    figure.savefig(output / "heldout-metrics.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(11, 4.5))
    for method in methods:
        data = predictions[predictions.method == method]
        annual = data.groupby("year").prediction.mean()
        axis.plot(annual.index, annual, "o-", label=method.replace("_", " "), color=COLORS[method], lw=1.4)
    reference = predictions[predictions.method == methods[0]].groupby("year").activity_reference.mean()
    axis.plot(reference.index, reference, "o--", color="#345e8a", label="MODIS reference", lw=1.5)
    axis.axvspan(min(evaluation["protocol"]["test_years"]) - .4, max(evaluation["protocol"]["test_years"]) + .4,
                 color="#c9d7e6", alpha=.25, label="held-out years")
    axis.set(xlabel="UTC year", ylabel="Mean paired-bin activity", title="Overlap comparison · changing seasonal support; descriptive only")
    axis.legend(ncol=3, fontsize=8)
    axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(output / "overlap-series.png", dpi=180, bbox_inches="tight")
    plt.close(figure)
