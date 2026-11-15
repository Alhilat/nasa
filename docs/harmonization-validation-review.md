# MODIS–VIIRS validation review

## Decision

Neither candidate is accepted for operational use. The application retains
separate native sensor series; it does not apply either candidate. These are
thermal detections and derived detection activity, not unique fires. The
2013–2025 studies below are unchanged in scope by the later 2000–2012 and 2026
archive import; the expanded archive has not been used to revalidate them.

The current workflow compares daytime VIIRS S-NPP with MODIS Aqua on 5 km
equal-area cell-days, then summarizes monthly. It preserves other sensors and
night observations separately. The common grid reduces pixel multiplicity,
but cannot make sensor sensitivity or observation opportunity equivalent.
NASA describes the finer 375 m VIIRS product as more responsive to small fires
than coarser 1 km products; actual overpasses and cloud masks also matter.
[NASA VIIRS product](https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html),
[NASA MODIS fire guide](https://www.earthdata.nasa.gov/sites/default/files/imported/MODIS_C6_Fire_User_Guide_B.pdf).

## Evidence from the held-out tests

Models used 2013–2019 for training, 2020–2021 for selection, and 2022–2025 for
the temporal test. The Jordan northeast block and Lebanon in the supplementary
Levant study were held out geographically. The reference is MODIS Aqua, not
independent fire truth. Errors below are reported flagged-cell days per 1,000
km² per month, conditional on paired detection-supported bins.

| Study | Selected candidate | Temporal pairs | Baseline MAE | Candidate MAE | Decision |
| --- | --- | ---: | ---: | ---: | --- |
| Jordan | regression | 31 | 0.29636 | 0.04305 | Reject: trend and seasonal profile not estimable; no regional test pairs |
| Levant | quantile mapping | 74 | 0.55600 | 0.04804 | Reject: temporal trend error worsened 19.5%; regional trend not estimable |

Jordan has 95 paired and 529 unpaired region-month bins overall; Levant has
326 paired and 142 unpaired. These are not samples of all observed and
unobserved opportunities. Missing months were not replaced with zeros. The
original detailed reports and diagnostics are
[Jordan](reports/harmonization/jordan/report.md) and
[Levant](reports/harmonization/levant/report.md).

## Seasonal and trend checks

The original evaluation reported agreement separately by calendar quarter,
but did not have an explicit seasonal-pattern acceptance gate. This review
adds one **after examining the original results**, so it is a retrospective
diagnostic, not a prospectively preregistered result. For each region-year
with at least one paired bin in each quarter, it compares centered quarterly
mean profiles with the reference. At least three distinct years are required;
each held-out scenario must have estimable support and calibrated profile MAE
no more than 10% above baseline, with a small numerical tolerance. This check
does not prove preservation of within-quarter timing or annual amplitude.

Rerunning the original inputs with that gate gave:

| Scenario | Jordan profile MAE, baseline → calibrated | Levant profile MAE, baseline → calibrated |
| --- | --- | --- |
| Held-out years | Not estimable | 0.25098 → 0.02656; 5 region-years across 4 years |
| Held-out region | Not estimable | Not estimable |
| Held-out years and region | Not estimable | 1.37047 → 0.45133; 3 region-years across 3 years |

The matched-calendar trend test separately requires at least three years and
six common months per region. Levant's temporal slope error increased from
0.01781090 to 0.02129142, exceeding the allowed 10% worsening. Sparse support
makes the regional and Jordan trend tests unestimable. Improved seasonal MAE
on the available Levant subset does not overcome these failures or show an
unbiased all-month relationship.

The rerun evaluations, including all splits and reasons, are
[Jordan JSON](reports/harmonization/jordan/season-review-evaluation.json) and
[Levant JSON](reports/harmonization/levant/season-review-evaluation.json). Their
study IDs are `a34b96950f8d996199d0fea752b4c2b161d536e61cb69e77e080c7c5732f7643`
and `0c9edb4da8f704d7903a0a4820622aa8cc87b292c4e8c45f773b24f50a94d617`.
Full rerun artifacts remain in ignored `reports/harmonization/*-season-review`.

## What is needed before another acceptance attempt

1. Obtain matched MODIS Aqua and VIIRS S-NPP swath, geolocation, fire-mask,
   cloud and quality information for the same area and day/night stratum.
   Build an independently audited cell-day observability manifest, including
   valid non-detection opportunities and overpass time differences. The
   point-only FIRMS CSVs cannot supply this denominator. Use common observable
   area-days and retain unknowns; do not infer clear views from detections.
2. Use a consistent, documented standard-product version across the overlap,
   or explicitly validate version transitions. Current MODIS native labels
   include `6.03`, `6.2` and `61.03`; do not assume these labels are equivalent.
   Keep NRT and standard revisions separate until a replacement policy is audited.
3. Increase independent regional and year coverage, especially low-activity
   and missing-observation conditions. Validate geographic transfer, not just
   a dense sample of points from the same area. Account for differences in
   overpass time, viewing geometry, cloud, resolution and small-fire sensitivity;
   compare grid size/origin and day versus night as sensitivity analyses.
4. Lock the intended population, target, input versions, split and acceptance
   thresholds before a new evaluation. Require the existing minimum coverage,
   agreement, bias, extrapolation, trend and all three blocked holdout gates,
   plus the new seasonal gate; include uncertainty and seasonal support in the
   report. More stringent seasonal sampling and independent reference data are
   needed before interpreting this as physical activity rather than a proxy.
5. Only after the declared checks pass for a specific sensor/product/area scope
   should the application expose an explicitly labeled, versioned estimate,
   with native series and missingness retained. No model is promoted by this review.

Reproduce with the commands in [methodology §8](harmonization-methodology.md#8-reproduce-the-analysis),
using new output directories. Supply a real, independently curated `--exposure`
file for the occupancy method; none is available in the present archive. The
experimental seasonal gate has been tested with synthetic fixtures only;
those fixtures are not scientific observations.
