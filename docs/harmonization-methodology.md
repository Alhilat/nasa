# FireScope MODIS/VIIRS harmonization methodology

Version: `sensor-calibration-v1` / `equal-area-cell-day-v1`. This document describes an experimental statistical comparison of reported thermal activity. It does not establish fire-event counts, burned area, completeness of observation coverage, or physical fire truth.

## Scientific decision

**Calibration is a candidate to test, never a default scientific fact.** Raw detections remain sensor-specific and immutable. Statistical estimates live in separate versioned artifacts. A fitted relationship is not automatically enabled: training, validation, held-out years, held-out regions, common observability, product consistency, extrapolation and trend-support checks must all pass.

The real Jordan demonstration declines operational calibration, even though regression reduces error against the MODIS reference in the paired temporal sample. Its regional test and trend support are inadequate, observability is unknown, and native product labels change. The separate Levant benchmark evaluates geographical transfer without replacing or retroactively improving the Jordan verdict. See the generated result reports for measured outcomes.

## 1. Define the observation and comparison target

A FIRMS hot spot is a satellite detection of a thermal anomaly, not a unique fire event. Small-fire sensitivity, pixel geometry, clouds, view angle, local acquisition time and repeat observations can differ across sensors. NASA’s VIIRS product documentation describes its algorithm heritage and nominal approximately 01:30/13:30 local observation cycle; this does not imply that every actual Aqua and S-NPP observation is contemporaneous. [NASA VIIRS Fire ESDR](https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html), [NASA FIRMS interpretation notes](https://firms.modaps.eosdis.nasa.gov/alerts/notes.php).

Default comparison: **VIIRS S-NPP → MODIS Aqua**, using daytime detections only. Aqua and Terra are retained separately; their counts are not pooled into an instrument total for fitting. Nighttime data are also retained in the activity audit and can be evaluated in a separate run. The arrows designate a numerical reference scale; MODIS is not ground truth or necessarily the more sensitive instrument.

The study includes all validated reported thermal-anomaly types and native confidence classes. It does not recode confidence as a probability, filter industrial/persistent heat through an undocumented rule, or claim all detections are vegetation fires. FRP, native confidence and scan/track fields remain available through the original source archive and ingestion records; FRP is not used as an interchangeable cross-sensor count substitute.

## 2. Spatial and temporal support

- Equal-area projection: EPSG:6933. Regions beyond ±86° latitude are rejected for this implementation.
- Default common cell: 5 km × 5 km, anchored at projected coordinate (0,0). Cell indices are `floor(x/5000), floor(y/5000)`.
- Base temporal unit: UTC calendar day; summary bin: UTC calendar month.
- A cell-day is flagged once if it contains one or more retained detections of the same sensor and day/night stratum. Multiple VIIRS pixels and repeated same-day observations do not increase that binary flag.
- This reduces sensitivity to pixel multiplicity. It does **not** correct missed small fires, cloud masking, view geometry, or unmatched acquisition times.
- Study area weights use each grid cell’s intersection with the region polygon. Cells with positive area in multiple study regions are excluded from all regions, avoiding shared coarse cells between spatial training and holdout groups.
- Detections outside the supplied boundaries or excluded cells are counted explicitly in the audit. Source records remain intact.

The Jordan starter clips a published Natural Earth 1:110m country outline into four study blocks. These are not administrative regions. The supplementary Levant study uses the country polygons of Jordan, Syria and Lebanon. Boundaries are approximate; they are neither cadastral nor a statement about disputed borders. Geometry bytes/source hashes and retained region areas are included in the experiment manifest. [Natural Earth data and license](https://www.naturalearthdata.com/about/terms-of-use/).

The CLI accepts different grid sizes from 1–50 km. That is a sensitivity-analysis option, not evidence that the default is optimal. The demonstrated results use 5 km; they do not establish stability to cell size, grid origin or temporal-bin changes.

## 3. A consistent activity metric, with explicit coverage limits

### Primary metric when independently curated observability is available

For sensor `s`, region `r` and month `t`, define:

```text
occupancy(s,r,t) = Σ[ a(c,r) × detected(s,c,d) ] / Σ[ a(c,r) ]
```

The sums range over **the same observable cell-days for both compared sensors**, in the same day/night stratum. `a(c,r)` is clipped cell area; `detected` is a binary detection flag. The denominator is an area-day exposure, and the result is a fraction in [0,1]. This is the fraction of eligible common cell-days flagged by a thermal detection, **not a fraction of land burned**.

An optional CSV exposure manifest must contain:

```text
sensor_code,day,grid_x,grid_y,daynight,observable
```

`observable` must be a real Boolean asserting curator-established sufficient valid observation opportunity for that common cell-day/stratum. It must come from independently checked swath/quality/cloud and sampling information; it cannot be derived by treating a detection as coverage or by declaring all calendar days clear. Unknown/absent exposure rows remain unknown. Duplicate exposure keys are rejected, including duplicates after date/index normalization.

Only cell-days declared observable for **both** sensors enter the numerator or denominator. Both sensors must share at least 80% of the retained region area-day support in a month by default; otherwise the monthly activity is null and excluded from calibration. With supplied observable support, an observable cell-day with no detection can legitimately contribute a zero. Without that support, it cannot.

### Detection-only fallback for FIRMS point CSVs

Hotspot-only CSVs do not supply the non-detection and valid-view information needed for the primary denominator. The fallback is therefore:

```text
reported activity(s,r,t) = 1000 × distinct reported hot-spot cell-days / retained region area(km²)
```

Units: reported flagged-cell days per 1,000 km² per month. There is no inferred observation-day denominator. No-detection bins are **unknown**, not zero. A complete region/month calendar is exported with null values for missing sensors, including months in which both are missing. Only finite paired bins enter comparison.

The resulting calibration is a **conditional comparison of detection-supported months**. It is subject to selection bias: low activity and missed detections influence which bins are paired. It cannot estimate an all-month cross-sensor relationship or coverage-normalized fire activity. The workflow refuses operational calibration for this metric regardless of attractive error scores or an incorrectly relabeled coverage flag.

## 4. Source provenance, overlapping years and product versions

`prepare-jordan` downloads the official country CSVs listed in NASA’s public file manifest for complete overlapping calendar years 2013–2025. `prepare-levant` prepares the separate three-country transfer study. Files are retained byte-for-byte with URL, retrieval timestamp, size-limited download, SHA-256 and strict field validation. A cached input must match its manifest checksum; changed sources require an explicitly new archived study. [NASA yearly-country access](https://firms.modaps.eosdis.nasa.gov/country/), [official file manifest](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt).

Original raw payload equality, resolved satellite and processing level identify exact repeats for this analysis. Different measurements, fields, times, versions and satellites remain distinct. The activity metric’s later cell-day flag is an aggregation operation, not a declaration that all contributing records describe one fire.

Native `version` strings are recorded without silently translating them into collection identifiers. The downloaded Jordan history contains MODIS strings `6.2`, `6.03` and `61.03`, and VIIRS string `2`. These should not be silently described as one unchanged Collection 6.1 product. The API’s historical sample also returned its own native version string. The experiment explicitly permits **exploratory product-transition evaluation**, exports product-stratified errors, and bars operational support when multiple native product labels occur. Applying these models to a verified C6.1-only archive requires a separately versioned, consistent-product analysis.

The supplied MAP_KEY was verified against NASA’s availability endpoint and retained only in ignored `.env`. No key-bearing request URL is stored in source manifests or results. Current availability, rather than an extrapolated end date, governs recent API requests. The historical benchmark uses public standard-product CSVs and does not spend thousands of API transactions downloading multi-year point histories. [NASA API availability](https://firms.modaps.eosdis.nasa.gov/api/data_availability).

## 5. Three candidate methods

All candidates operate on the same paired activity units. Training includes finite nonnegative pairs only, with no interpolation across missing months.

1. **Baseline aggregation**: identity mapping of source common activity. It is a structural comparison, not a calibrated sensor-equivalence claim.
2. **Seasonal regression**: ordinary least squares of `log1p(reference activity)` against intercept, `log1p(source activity)`, and annual/semiannual sine/cosine terms. Coefficients are fitted with NumPy least squares. A negative source-response slope or rank-deficient fit is rejected. Back-transformation is `max(0, expm1(fitted log response))`, clipped to [0,1] only for occupancy. There is no lognormal smearing correction, so the estimate should not be called an unbiased arithmetic conditional mean. Its original-unit bias is evaluated explicitly.
3. **Seasonal empirical quantile mapping**: 101 linearly interpolated empirical quantiles fitted separately by calendar quarter. Repeated source quantiles receive the mean of corresponding reference quantiles, giving a deterministic monotone transfer. A quarter needs at least eight training pairs and three distinct source values; otherwise it uses an explicitly recorded global-training fallback. This does not create additional observations. Unseen tails are clipped to the training boundary and flagged as extrapolation. [NumPy quantile definition](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html).

Seasonal terms, empirical distributions, fallback decisions and input ranges are derived from training data only. The regression’s harmonic seasonality is smooth; quarter-wise quantile mapping may have seasonal-boundary discontinuities. Neither method assumes stationary bias has been demonstrated.

Out-of-range inputs are counted for every split. Statistical intervals are withheld for extrapolated predictions. Missing activity inputs stay missing. Coefficients, quantile knots, fallbacks and source ranges are stored as JSON, never executable pickles.

## 6. Train/validation/test design and acceptance

Both checked-in protocols fix these disjoint chronological sets:

| Role | UTC years |
| --- | --- |
| Training | 2013–2019 |
| Validation for candidate selection | 2020–2021 |
| Untouched temporal test | 2022–2025 |

Jordan: northeast study block held out; remaining blocks are eligible training regions. Levant: Jordan and Syria eligible for training; Lebanon held out. The latter is explicitly supplementary exploratory transfer validation, not a replacement for the unsuccessful Jordan regional test.

Five split labels are preserved: training, validation in training regions, held-out years in training regions, held-out region during training years, and held-out years in the held-out region. Held-out-region validation-year bins are labeled excluded. No held-out target values are used in fitting, seasonality estimation, intervals for fitted parameters, or candidate selection.

Minimum defaults: 24 training pairs across at least three years, eight evaluation pairs per relevant test scope, and adequate source/reference variation. Validation qualification requires at least a 10% reduction in both MAE and RMSE against baseline, no increase in absolute bias, and no more than 10% extrapolated inputs. Among qualifying candidates, minimum validation MAE determines the selected method. Ties are deterministic. If that method fails test criteria, the code refuses support; it does not choose another method using test scores.

Support additionally requires improvement in all three held-out scenarios, adequate pairs for each held-out region, estimable stable trends, independently supplied observability and a consistent native-product scope. A passing result would support only the declared metric, products, sensors, strata, grid, regions and periods. The real demonstrated results are not automatically promoted.

The later [seasonal validation review](harmonization-validation-review.md) adds a
separate seasonal-profile gate. This gate was added after the original studies
were examined; it was not prospectively specified for those studies.

This is a fixed blocked split, not exhaustive cross-validation or a claim of prior scientific preregistration. Spatial exclusion of shared cells prevents direct coarse-cell leakage but not broader environmental dependence or spatial correlation. Two or three countries do not establish global transferability.

## 7. Accuracy, trend stability and uncertainty

For paired bins, error is `calibrated estimate − reference activity`. The report includes:

- MAE: mean absolute error.
- RMSE: square root of mean squared error.
- Bias: mean signed error, positive when the source/estimate exceeds the reference.
- Paired sample counts and extrapolation fractions for every split.
- Region, calendar-quarter and native-reference-product breakdowns.

**Trend stability** uses only calendar months present in every compared year for a region. At least three years and six common months are required by default. Linear slopes of annual mean matched-month activity are computed for source, reference and each estimate. The report retains calibrated/reference slope error, baseline/reference slope error and change from the source slope. Support is refused if trend error worsens by more than 10% plus numerical tolerance. If comparable seasonal support is absent, the slope is not estimated. A plot of annual means with changing sampled seasons is labeled descriptive and is not substituted for this trend test.

This matters because distributional bias adjustment can alter trends and extrapolation behavior. Evidence from bias-adjustment research motivates checking those effects; it does not validate this particular fire-activity calibration. [Spuler et al., 2024](https://gmd.copernicus.org/articles/17/1249/2024/), [Berg et al., 2024](https://gmd.copernicus.org/articles/17/8173/2024/).

Uncertainty is limited to statistical quantities supported by the input:

- Fixed-model error intervals resample whole held-out year blocks, retaining all within-year months/regions; at least three blocks are required.
- Parameter intervals refit candidates on resampled training-year blocks, using seed 2026 and 200 replicates by default. The 2.5/97.5 percentiles describe mapping-parameter variability, not prediction intervals. Too many failed fits or insufficient years leave intervals null.
- These intervals do not quantify geolocation error, missed fires, product uncertainty, spatial transfer uncertainty, cross-year dependence, physical fire occurrence or causal uncertainty. Four held-out years provide a weak basis for interval calibration. No physical uncertainty value is invented from nominal pixel size or native confidence.

## 8. Reproduce the analysis

Run from the repository root. Install the locked environment and local packages as in the README. PowerShell examples:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend -e ./data-pipeline
.\.venv\Scripts\python.exe -m firescope_pipeline.cli prepare-jordan --output data/harmonization/jordan
.\.venv\Scripts\python.exe -m firescope_pipeline.cli harmonize --manifest data/harmonization/jordan/sources.json --regions data/harmonization/jordan/regions.geojson --protocol configs/harmonization/jordan-protocol.json --output reports/harmonization/jordan-new-run
```

Supplementary external-region validation:

```powershell
.\.venv\Scripts\python.exe -m firescope_pipeline.cli prepare-levant --output data/harmonization/levant
.\.venv\Scripts\python.exe -m firescope_pipeline.cli harmonize --manifest data/harmonization/levant/sources.json --regions data/harmonization/levant/regions.geojson --protocol configs/harmonization/levant-protocol.json --output reports/harmonization/levant-new-run
```

Output directories must be new or empty. Results are never silently overwritten. On Bash use `.venv/bin/python`. To evaluate the primary occupancy metric, supply `--exposure path/to/independently-curated-exposure.csv`; the same checks and holdouts still apply. No exposure fixture is presented as real scientific data.

Every run exports sensor-level normalized input/audit CSVs, monthly activity, grid areas, the complete paired/missing calendar, split-labeled candidate estimates and parameter intervals, fitted model JSON files, evaluation JSON, PNG/SVG comparisons, a results report and an artifact SHA-256 manifest. The manifest records source hashes, geometry hash, analysis-code hash and dependency versions. Model identifiers hash training data, fitted parameters, algorithm, metric and scope. Repeated runs in the same locked environment should reproduce those artifacts; numerical/plot bytes across different OS/BLAS/font/projection versions are not guaranteed identical.

## 9. Optional database registration and API

The computational study runs without PostGIS. With a configured database:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m firescope_pipeline.cli register-calibration reports/harmonization/jordan-new-run
```

Migration `0003_calibration` adds immutable `calibration_models`. Registration verifies artifact hashes and model-version hashes before an analysis job stores models, validation details and source provenance. A repeated model version is idempotent. Operationally unsupported models stay `candidate_only`; observations and existing aggregates are not modified. Results also enter the versioned `analytical_results` table. `GET /api/v1/calibration-models/{sha256}` exposes the model with validation scope; it does not imply deployment or apply a mapping to an unvalidated domain.

No forecast or neural model is implemented. These are explicitly requested classical statistical calibration experiments. No retraining, promotion or public upload of keys occurs automatically.

## 10. Verification and remaining limits

Unit tests cover common cell-days, independent sensor counts, unknown versus exposed zero, matching observability, minimum coverage, region boundary exclusion, time-zone validation, duplicate exposure keys, exact recovery of a known synthetic regression, monotone tied quantiles, extrapolation, missingness, blocked-split leakage, metric signs, trend-support requirements, deterministic block intervals, model hashes and registration hash checks. Synthetic numbers are confined to tests and are not fire observations.

Real-data runs use downloaded NASA CSVs. Local PostgreSQL/PostGIS integration cannot be claimed without a running service; database registration/immutability tests are included in the PostGIS suite and CI. See [verification results](verification.md) for checks actually executed and [the scientific interpretation contract](science.md) for broader limitations.
