# PIRX visual identity

## Scientific Editorial × Earth Observation

The existing PIRX name and supplied project logo anchor the identity. The application combines warm editorial surfaces with navy analytical workspaces. Space Grotesk headlines, fine rules and compact monospace annotations establish the hierarchy. Existing Lucide line icons provide a consistent interface vocabulary.

## Color system

| Token | Color | Application |
| --- | --- | --- |
| Deep Space Navy | `#101D35` | Maps, analytical panels, charts, documentary image captions |
| NASA-inspired Blue | `#1769AA` | Navigation, primary actions, links, filters, scientific references |
| Fire Orange | `#F47A32` | Observed detections, activity series, calendar intensity |
| Alert Red | `#D94141` | Reserved for independently established critical fire alerts or high-severity indicators |
| Warm Ivory | `#F4F2EB` | Page canvas, navigation, editorial secondary surfaces |
| Pure White | `#FFFFFF` | Information panels, analytical foreground text |
| Graphite | `#252B35` | Editorial text and headings |
| Muted Gray | `#8B929C` | Neutral status marks, unknown-data marks on navy |

Supporting values derive from these roles. Editorial supporting text uses `#525D6B`, navy supporting text uses `#BCC7D6`, and scientific references on navy use `#8CC4EE`. Borders use `#CDD1D5` on light surfaces and `#40516A` on dark surfaces. These text combinations exceed WCAG AA's 4.5 to 1 normal-text contrast requirement. Orange calendar fills carry navy text. Keyboard focus uses the surface's blue link color.

The reserved alert color requires a scientifically supported severity state. Archive outages and ordinary statistical anomalies use informational styling with explicit text. Monthly calendar intensity continues to follow the existing calculation.

## Typography

| Family | Role | Scale |
| --- | --- | --- |
| Space Grotesk | Page headlines, section headings, prominent observations | 36–54 px page headlines, 18–28 px section headings |
| Inter | Navigation, controls, explanations, body copy | 12–14 px UI, 14 px body copy |
| IBM Plex Mono | Coordinates, timestamps, statistical values, chart axes, technical annotations | 10–13 px annotations, 26–38 px statistics |

The fonts are self-hosted in `frontend/public/fonts`. Their SIL Open Font License files accompany each family. Font sources are the official Google Fonts repository's `ofl/spacegrotesk`, `ofl/inter` and `ofl/ibmplexmono` directories.

## Composition and interaction

- Use the existing responsive workspace grid and route hierarchy.
- Place large left-aligned headlines above a thin divider, with supporting copy beneath them.
- Use ivory for orientation and white for filters, provenance and explanations. Navy distinguishes map and analytical workspaces.
- Use 2–3 px corner radii, one-pixel borders and generous 20–32 px panel insets.
- Use blue for selection and actions. Pair color states with labels, outlines, icons or shapes.
- Preserve visible focus rings, the skip link, accessible chart tables and reduced-motion support.
- Keep mobile forms stacked and wide scientific tables horizontally scrollable inside their panels.

## Maps and charts

Map backgrounds use navy. Authentic Esri imagery retains its original colors and attribution. Region selections use a fine, dashed blue reference line. MODIS markers use fire orange circles. VIIRS uses a lighter orange with a square legend swatch. Existing sensor labels and chart line patterns retain their meaning.

Charts use navy backgrounds, light monospace axes and restrained dashed grid lines. Observations use orange, the historical median uses light blue, and the upper percentile uses white. Legends name each series, and missing values continue to break lines. Rendering tokens live in `frontend/src/visualTheme.ts`, while CSS surface tokens live in `frontend/src/identity.css`.

## Documentary imagery

The Methods page uses NASA's uncropped 1280 × 853 rendition of the Aqua MODIS image of Quebec acquired on June 3, 2023. Its caption identifies the instrument, place, acquisition date and documentary role. The visible credit acknowledges Lauren Dauphin and NASA Earth Observatory, using MODIS data from NASA EOSDIS LANCE and GIBS/Worldview. The caption links to the original article. [NASA Earth Observatory source](https://science.nasa.gov/earth/earth-observatory/fires-burn-across-quebec-151430/)

The local file is `frontend/public/images/quebec-aqua-modis-20230603.jpg`. The original download is available from NASA's asset service. [Original NASA image](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/imagerecords/151000/151430/quebecfires_amo_2023154.jpg)

Use documentary imagery at its natural aspect ratio with a caption and source. Project branding uses the existing PIRX asset. NASA references credit the data and imagery providers.

## Verification

- The production TypeScript and Vite build succeeds.
- All 64 frontend tests and 233 runnable Python tests pass. Fifteen PostGIS integration tests require a database and were skipped.
- Restored controls, source content, map tools and export actions are documented in the component restoration report.
- Desktop and mobile review covers all five routes and the existing map. The local backend is offline, so real-data charts, API exports and Gemini responses require live verification after service startup.
- PNG generation and its download handler pass automated tests. File-saving completion in the preview browser remains unconfirmed.

[Component restoration report](reports/component-restoration.md)
