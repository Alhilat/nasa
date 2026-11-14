from dataclasses import dataclass
from datetime import datetime

from shapely.geometry import Point, shape

from app.schemas import ObservationQuery

JORDAN_BBOX = (34.8, 29.0, 39.4, 33.5)
JORDAN_START = "2013-01-01T00:00:00Z"
JORDAN_END = "2026-01-01T00:00:00Z"


@dataclass
class Selection:
    bbox: tuple[float, float, float, float] | None = None
    polygon: dict | None = None
    start: datetime | None = None
    end: datetime | None = None

    def __post_init__(self):
        validated = ObservationQuery(
            bbox=self.bbox, polygon=self.polygon, start=self.start, end=self.end,
        )
        self.bbox, self.polygon = validated.bbox, validated.polygon
        self.start, self.end = validated.start, validated.end
        self._geometry = shape(self.polygon) if self.polygon else None

    def includes(self, row: dict) -> bool:
        if self.start and row["acquired_at"] < self.start:
            return False
        if self.end and row["acquired_at"] >= self.end:
            return False
        lon, lat = row["longitude"], row["latitude"]
        if self.bbox:
            west, south, east, north = self.bbox
            longitude_in = west <= lon <= east if west < east else lon >= west or lon <= east
            if not longitude_in or not south <= lat <= north:
                return False
        return self._geometry is None or self._geometry.covers(Point(lon, lat))

    def as_dict(self):
        return {"bbox": list(self.bbox) if self.bbox else None, "polygon": self.polygon,
                "start": self.start.isoformat() if self.start else None,
                "end": self.end.isoformat() if self.end else None}
