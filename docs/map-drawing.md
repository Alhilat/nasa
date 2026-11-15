# Map region drawing and coordinates

The dashboard uses `terra-draw` with `terra-draw-maplibre-gl-adapter`, including
`TerraDrawRectangleMode` and `TerraDrawPolygonMode`. The adapter handles pointer
interaction, vertex previews and geometry completion; custom map-click drawing
logic has been removed. Rectangle completion uses two opposite corners. Polygon
completion uses the first vertex or Enter; self-intersection validation is enabled.

The toolbar cancels with Escape or **Cancel drawing**, clears the region, and can
use the current map bounds. Cancelling restores navigation and observation
inspection. A basemap retry rebuilds the adapter against the new style; cleanup
stops it before removing the map. Original observation layers and exports remain
available.

**Enter latitude / longitude** exposes labeled South/North latitude and West/East
longitude fields in WGS84 decimal degrees. The form rejects empty, nonfinite,
out-of-range and zero-area bounds. West greater than east produces a split
MultiPolygon across the antimeridian. Drawn edges crossing the antimeridian are
rejected with directions to use this form or split GeoJSON instead.

Both tools produce the same typed Polygon/MultiPolygon region. The parent page
clears stale completeness declarations and marks the new selection pending.
**Apply filters** updates the map query and historical analysis together. Drawing
and coordinate entry do not fetch observations on their own.

Tests cover drawing completion, cancel/clear, antimeridian rejection, adapter
cleanup, tile retry, observation inspection and coordinate validation. The real
map was also checked with rectangle and polygon pointer interactions and manual
coordinate entry. Library integration follows the
[Terra Draw guide](https://github.com/JamesLMilner/terra-draw/blob/main/guides/1.GETTING_STARTED.md).
