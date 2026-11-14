import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.validation import explain_validity


class ObservationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bbox: tuple[float, float, float, float] | None = None
    polygon: dict[str, Any] | None = None
    start: datetime | None = None
    end: datetime | None = None
    sensors: list[str] = Field(default_factory=list, max_length=10)
    confidence: Literal["low", "nominal", "high"] | None = None
    limit: int = Field(default=2000, ge=1, le=5000)
    offset: int = Field(default=0, ge=0, le=1000000)

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, value):
        if value is None:
            return value
        west, south, east, north = value
        if not all(math.isfinite(x) for x in value):
            raise ValueError("Bounding box coordinates must be finite")
        if not (-180 <= west <= 180 and -180 <= east <= 180 and west != east):
            raise ValueError("Longitude bounds must be distinct and within [-180, 180]")
        if not (-90 <= south < north <= 90):
            raise ValueError("Latitude bounds must satisfy -90 <= south < north <= 90")
        return value

    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, value):
        if value is None:
            return value
        if value.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Provide a GeoJSON Polygon or MultiPolygon geometry")
        try:
            geom = shape(value)
            if geom.is_empty or not geom.is_valid:
                raise ValueError(f"Invalid polygon: {explain_validity(geom)}")
            if geom.has_z:
                raise ValueError("Use 2D WGS84 coordinates")
            polygons = [geom] if geom.geom_type == "Polygon" else geom.geoms
            vertices = 0
            for polygon in polygons:
                for ring in [polygon.exterior, *polygon.interiors]:
                    coords = list(ring.coords)
                    vertices += len(coords)
                    for lon, lat in coords:
                        if not (math.isfinite(lon) and math.isfinite(lat)):
                            raise ValueError("Polygon coordinates must be finite")
                        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                            raise ValueError("Polygon must use WGS84 longitude/latitude")
                    if any(abs(a[0] - b[0]) > 180 for a, b in zip(coords, coords[1:])):
                        raise ValueError("Split antimeridian polygons into a MultiPolygon")
            if vertices > 10000:
                raise ValueError("Polygon exceeds 10,000 vertices")
        except (TypeError, KeyError, IndexError, AttributeError, GEOSException) as exc:
            raise ValueError("Malformed GeoJSON polygon") from exc
        return value

    @field_validator("start", "end")
    @classmethod
    def aware_time(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone, preferably Z (UTC)")
        return value

    @model_validator(mode="after")
    def valid_range(self):
        if self.start and self.end and self.start >= self.end:
            raise ValueError("start must precede end (end is exclusive)")
        return self
