import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app


@pytest.fixture
def client():
    class UnavailableSession:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("test", {}, Exception("credential-must-not-leak"))

    app.dependency_overrides[get_session] = lambda: UnavailableSession()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_liveness_and_public_configuration_do_not_require_database(client):
    assert client.get("/api/v1/health/live").json()["status"] == "ok"
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    assert response.json()["features"]["machine_learning"] is False
    assert response.json()["features"]["forecasting"] is False
    assert "database_url" not in response.text.lower()
    assert "password" not in response.text.lower()


def test_database_failure_is_explicit_and_sanitized(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "credential-must-not-leak" not in response.text


@pytest.mark.parametrize("query", [
    "bbox=0,1,2", "bbox=0,nan,2,3", "bbox=0,4,2,3", "bbox=-181,0,10,20",
    "start=2024-01-01T00:00:00", "start=2024-02-01T00:00:00Z&end=2024-01-01T00:00:00Z",
    "limit=5001", "offset=-1", "sensors=UNKNOWN", "confidence=probability",
])
def test_invalid_get_queries_return_422(client, query):
    assert client.get(f"/api/v1/observations?{query}").status_code == 422


@pytest.mark.parametrize("polygon", [
    {"type": "Point", "coordinates": [0, 0]},
    {"type": "Polygon", "coordinates": []},
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]},
    {"type": "Polygon", "coordinates": [[[179, 0], [-179, 0], [-179, 1], [179, 0]]]},
    {"type": "Polygon", "coordinates": [[[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 0, 1]]]},
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},
    {"type": "Polygon", "coordinates": [[1, 2, 3]]},
])
def test_invalid_polygons_return_422(client, polygon):
    response = client.post("/api/v1/observations/query", json={"polygon": polygon})
    assert response.status_code == 422


def test_openapi_documents_query_and_operations(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/observations/query" in paths
    assert "/api/v1/aggregates/{job_id}" in paths
