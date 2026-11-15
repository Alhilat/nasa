# PIRX visual identity

## Scientific Editorial × Earth Observation

The existing responsive workspace uses one continuous warm ivory canvas. Hierarchy comes from typography, alignment and whitespace. Navigation, analytical panels, charts, map containers, image captions and conversation panels share that surface. Controls retain the boundaries needed to understand and operate them.

## Approved palette

| Color | Value | Role |
| --- | --- | --- |
| Warm Ivory | `#F4F2EB` | Page, navigation, panels, map containers and chart backgrounds |
| White | `#FFFFFF` | Input fields, tooltip surfaces and selected controls |
| Graphite | `#252B35` | Headings, body copy, data labels and percentile reference lines |
| NASA Blue | `#1769AA` | Links, actions, focus, VIIRS series and geographic selections |
| Fire Orange | `#F47A32` | MODIS series, observed activity and calendar intensity |
| Alert Red | `#D94141` | Existing error indicators; it does not imply a new scientific alert |
| Muted Gray | `#8B929C` | Neutral marks and restrained scientific grid lines |

Supporting neutral shades and calendar ramps are mixtures of this palette. Small text uses graphite or a graphite-derived neutral, with gray reserved for marks rather than low-contrast body copy. Light styling is intentional even when the operating system prefers dark mode.

## Typography and composition

- Space Grotesk: headings and prominent editorial statements.
- Inter: body copy and interface controls.
- IBM Plex Mono: scientific values, dates, coordinates, axes and technical metadata.
- Existing self-hosted fonts, page routes, responsive grids and content remain in place.
- Decorative eyebrow slogans and framing rules are removed. Scientific labels, sensor names, units, provenance and caveats remain visible.
- Panels have no decorative outlines or alternating backgrounds. Form fields, focus rings, table headers and selected interactive calendar cells retain essential boundaries.
- Wide scientific tables remain independently scrollable and keyboard accessible.

## Maps and charts

The ArcGIS World Imagery and World Boundaries and Places sources, tile routes, imagery, attribution, layer identities, coordinates and observation values are unchanged. Only the map's empty background, surrounding controls, container and rendering colors use the updated palette. External imagery and the original documentary photograph retain their natural colors.

MODIS is orange and VIIRS is blue, with existing sensor names and legend shapes retained. Geographic selections retain their dashed outline. Charts use ivory backgrounds, graphite labels, orange observations, blue historical medians and graphite percentile lines. Scientific grid lines are quiet gray. Missing values continue to break chart lines; no measurements, calculations or thresholds change.

CSS layout and responsive behavior live in `frontend/src/styles.css`; the consolidated visual tokens and appearance live in `frontend/src/identity.css`. Canvas, SVG chart and MapLibre rendering tokens live in `frontend/src/visualTheme.ts`.

## Verification

The implementation's route screenshots, checks and verification results are saved in `reports/visual-cleanup/`. The application has no configured frontend lint script; the build performs TypeScript checking before Vite compilation. Existing frontend tests verify the preserved scientific and interaction behavior. Browser inspection covers every explicit route and the missing-route state at desktop and mobile sizes, plus map, chart, menu and expanded-filter states.
