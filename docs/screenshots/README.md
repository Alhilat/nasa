# Judge screenshots

These JPEGs were captured from the running local application on November 15,
2026, at its existing 1265 × 712 browser viewport. They show real NASA FIRMS
archive data, without fabricated observations or completeness declarations.

| File | View and provenance |
| --- | --- |
| [judges-dashboard.jpg](judges-dashboard.jpg) | Dashboard geographic map, shared MODIS/VIIRS colors, basemap attribution and displayed-point limit. |
| [judges-median-calendar.jpg](judges-median-calendar.jpg) | Jordan country boundary, 2013–2025, baseline 2013–2024, minimum five earlier reference years; Harmonized series with median-departure colors. Early/unsupported months are hatched and calibration remains experimental. |
| [judges-provenance.jpg](judges-provenance.jpg) | Original NASA archive source filenames, checksums and row counts in the Sources view. |

The [calendar verification record](../reports/judges-calendar-verification.json)
preserves the exact query, analysis ID, versions and export comparison results:
all 156 monthly CSV rows matched the API, with 96 assessed median comparisons.
The [backfill summary](../reports/backfill-judges-summary.json) records the
13,079-detection, 164-source archive and its explicit availability gaps.

Earlier PNG screenshots in this directory document previous development stages;
the three `judges-*.jpg` images are the current judge evidence.
