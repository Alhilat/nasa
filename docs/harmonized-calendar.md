# Harmonized activity calendar

The dashboard and History page offer **Harmonized / MODIS / VIIRS** views. History's
default sensor selection includes both families. Native views show the original
sensor counts, even when the separate approved historical-comparison layer has
calibrated values. Multiple satellites within a family remain separate.

`POST /api/v1/analytics/history` adds `harmonized_calendar`; existing `monthly`,
anomaly baselines and raw observations retain their contracts. The analysis
version is `historical-activity-v4`. Its fingerprint includes the calendar,
model artifact, approval state and intervals. Full analysis JSON and offline
`app.history_export` replay retain this result. The calendar's CSV button exports
the displayed snapshot, including interval bounds, provenance and model metadata.
The existing monthly CSV remains a sensor-specific anomaly export.

## A single reference scale

The pure `app.harmonized_calendar.build_calendar` function has no database,
network or filesystem access. Routes supply selected observations, archive
metadata and models; the history engine supplies native monthly counts.

An eligible approved VIIRS-to-MODIS model fixes the sensor pair first. Otherwise
the pair with the most usable paired months is chosen. Ties prefer Aqua over
Terra, then S-NPP over NOAA-20 over NOAA-21. That pair stays fixed throughout the
calendar; satellites are never silently switched or added together.

Each month uses, in order:

1. A complete native MODIS reference month.
2. A complete VIIRS month mapped to the reference scale.
3. An available positive MODIS reference count with unknown completeness.
4. An available positive mapped VIIRS count with unknown completeness.
5. Null when no usable estimate exists.

Only complete archive months may contribute zeros. Standard products are
required. NRT, mixed-processing revisions and partial sensor-start months are
excluded from fitting and the harmonized view. Native views retain the archive
records and their completeness context. Unknown completeness can support only
an explicitly conditional, experimental comparison; no unobserved zeros,
physical fire counts or observation exposure are invented.

## Reusing the existing models

The existing seasonal `fit_model` / `predict_model` regression and quantile
mapping functions are reused with `monthly_normalized_detection_count`.
Registered density or occupancy artifacts are never applied to raw counts and
models are never inverted to change their reference scale.

A registered model must pass the existing history fingerprint, approval,
metric, geographic scope, confidence, year interval, sensor and native product
version checks before it can produce a validated mapped month. Existing
candidate-only study artifacts are not promoted to approved models.

When no compatible approved model exists, both methods are fitted to standard
archive count pairs. At least 24 pairs spanning three earlier years and eight
pairs in a selection year are required. The latest overlap year with at least
eight usable pairs selects
the method by lowest MAE; it is a **selection set**, not an independent final
test. The chosen method is refitted on all paired months for the retrospective
calendar. A newer partial year does not disable earlier overlap. The artifact,
selected year, candidate errors and training-month
labels are returned. These fits are always experimental; they cannot change
the existing approval gates or supply anomaly baselines.

## Uncertainty and labels

The existing `parameter_intervals` function resamples entire overlap years,
refits the selected method 100 times using seed 2026, and returns 2.5th and
97.5th prediction quantiles. At least 50 successful fits are required. Bands
describe **fitted-parameter uncertainty**, conditional on the selected model
and archive. They exclude model-selection, observation and residual prediction
uncertainty, and cannot be interpreted as physical-fire confidence intervals.

Native MODIS reference values have unknown observational uncertainty and no
invented interval. Extrapolated regression values and clipped quantile tails
are flagged, remain experimental, and have no interval. Registered artifacts
whose actual training rows are unavailable also have unknown bands; refitting
the current selection would describe a different model.

Per-month `validation_status` is validated only for a compatible approved
mapping with complete archive support inside its fitted input range. Native
reference months carry an experimental calendar label and are identified as
native observations in the inspector. A calendar may carry a validated label
when an approved mapping is available and all populated mapped/reference
months meet its completeness/support requirements. This means agreement on
the approved sensor scale, never validation against physical fire truth.

## Contract and checks

The calendar also returns `median_comparison`, computed by the pure
`calendar_statistics.py` functions from complete earlier same-month values.
The UI's median color mode displays signed absolute departures, with unassessed
cells for missing support or unapproved mappings. Native views use native counts
of the same sensor. See [the accessibility and median contract](accessibility.md).

`app.calendar_schemas` defines the Pydantic response. Generate its TypeScript
types from the repository root:

```powershell
python scripts/generate_calendar_types.py
```

Use the installed project environment (`.venv/Scripts/python.exe` on Windows).
The contract test detects stale generated definitions. Numerical tests use
explicitly synthetic software fixtures for reference precedence, gap filling,
method selection, deterministic replay, year-block bands, unsupported tails,
missing/zero semantics, standard-product requirements and approval labels.
Frontend tests verify the toggle, original native values, interval shading,
missing months, accessible details and reproducible CSV exports.
