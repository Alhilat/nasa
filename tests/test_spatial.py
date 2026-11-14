import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import Observation
from app.repository import observation_filters
from app.schemas import ObservationQuery


def test_wrapped_bbox_produces_two_indexable_envelopes():
    query = ObservationQuery(bbox=(170, -10, -170, 10))
    sql = str(select(Observation.id).where(*observation_filters(query)).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert sql.count("ST_MakeEnvelope") == 2
    assert " OR " in sql
    assert "ST_Covers" in sql


def test_polygon_holes_and_boundary_geometry_accepted():
    polygon = {"type": "Polygon", "coordinates": [
        [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
        [[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]],
    ]}
    assert ObservationQuery(polygon=polygon).polygon == polygon


@pytest.mark.parametrize("bbox", [(0, 0, 0, 1), (0, 1, 1, 1), (0, 0, float("inf"), 1)])
def test_degenerate_bounds_rejected(bbox):
    with pytest.raises(ValueError):
        ObservationQuery(bbox=bbox)
