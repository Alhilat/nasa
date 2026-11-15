# Accessible scientific colors and median departures

All scientific color scales are defined in
[`frontend/src/colorScales.ts`](../frontend/src/colorScales.ts). The calendar
uses these values directly; chart/map sensor colors and CSS legend variables
consume the same definitions. Branding and surface colors remain in the separate
visual theme. No calendar scale is independently hardcoded in a stylesheet.

| Information | Scale | Additional visible cue |
| --- | --- | --- |
| Activity intensity | Five-step Cividis, increasing lightness | Numeric detections and lower/higher legend |
| Difference from historical median | Seven-step reversed ColorBrewer PuOr, purple below / orange above | Signed absolute departures, `0` at median, labeled legend |
| MODIS / VIIRS | Orange / sky blue from Okabe–Ito | Named sensors, circle/square chart markers and distinct line patterns |
| Missing or unassessed | Separate dark gray, hatched cells | `—`, reason in accessible name/title, explicit legend |

Text switches between black and white to maximize contrast against each cell
fill. Automated checks require **at least 4.5:1** on every scale color and on
unknown cells. The activity scale's relative luminance is strictly increasing.
Keyboard focus and selected-month outlines are retained. Chart data tables,
named fields and semantic table headers provide additional ways to read results.
These are targeted checks, not a claim that the entire application has undergone
a WCAG conformance audit or testing with every color-vision condition.

## How the median mode works

Choose **Calendar colors → Departure from historical median** independently of
the Harmonized / MODIS / VIIRS series toggle. The selection changes presentation;
it does not change the query, observations, calibration, or underlying trend.

The pure backend function in
[`calendar_statistics.py`](../backend/app/calendar_statistics.py) computes:

```text
departure = current value − median(eligible earlier values of the same calendar month)
```

Reference years must be inside the requested baseline interval and strictly
earlier than the target year. Both target and reference months need complete
archive support; the configured minimum reference count is respected. Native
views always compare native counts of the same sensor. The unified view uses
complete native MODIS reference months or compatible, approved mapped months.
Experimental mapped values, extrapolation and unsupported processing do not
receive assessed departures or enter a baseline.

The seven diverging classes split the maximum absolute assessed departure in
the current view into three equal magnitude bands on each side of zero. The
legend reports that view's symmetric extent. Zero uses a neutral center; darker
purple/orange means farther below/above the median. Calendar cell numbers show
signed **absolute** differences in the selected sensor/reference units. Changing
the view can change its scale; colors are not a fixed cross-region risk category.

An additional percentage departure is returned for positive medians. It remains
null when the median is zero; the finite absolute difference can still be shown.
Missing values, incomplete archives and insufficient history remain unassessed.
No missing month is silently substituted with zero or a pooled sensor count.

The `median_comparison` response carries the median, signed difference,
percentage when defined, actual reference years/sample size, status and reason.
It is included in generated TypeScript contracts, analysis JSON, harmonized CSV,
and the native calendar CSV's `median_comparison_json` column. The analysis
version is `historical-activity-v4`; the calendar version is `modis-calendar-v2`.

## Interpretation and reproduction

These are descriptive historical comparisons, not forecasts, probabilities or
physical-fire severity. Color does not upgrade an experimental calibration.
Model bootstrap bands retain their fitted-parameter meaning.

For a real assessed example, open History, choose the Jordan country boundary
in Advanced analysis settings, and analyze the archive. That boundary is covered
by the country sources. A larger study rectangle can legitimately remain
unassessed. No completeness declarations were invented for the screenshots.

Checks: [`test_calendar_statistics.py`](../tests/test_calendar_statistics.py),
[`colorScales.test.ts`](../frontend/src/colorScales.test.ts),
[`BurningCalendar.test.tsx`](../frontend/src/components/BurningCalendar.test.tsx),
[`HarmonizedCalendar.test.tsx`](../frontend/src/components/HarmonizedCalendar.test.tsx),
and [`ActivityChart.test.tsx`](../frontend/src/components/ActivityChart.test.tsx).

Palette and accessibility sources:

- [Matplotlib colormap guidance](https://matplotlib.org/stable/users/explain/colors/colormaps.html).
- [ColorBrewer specifications](https://github.com/axismaps/colorbrewer/blob/master/colorbrewer_schemes.js),
  including PuOr's colorblind-safe classification. Color specifications developed
  by Cynthia Brewer, Mark Harrower and The Pennsylvania State University.
- [Okabe and Ito: Color Universal Design](https://jfly.uni-koeln.de/color/).
- [W3C: Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).
- [W3C: Contrast Minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
