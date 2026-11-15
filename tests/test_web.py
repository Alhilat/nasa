import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import mount_website, router


@pytest.fixture
def website(tmp_path):
    (tmp_path / "index.html").write_text("<html>PIRX website</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('PIRX');")
    app = FastAPI()
    app.include_router(router)

    @app.get("/api/v1/health/live")
    def live():
        return {"status": "ok"}

    mount_website(app, tmp_path)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/explorer", "/history", "/sources", "/methodology"])
def test_pages_support_direct_navigation_and_refresh(website, path):
    response = website.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PIRX website" in response.text


def test_assets_and_api_keep_their_own_responses(website):
    assert "console.log" in website.get("/assets/app.js").text
    assert website.get("/api/v1/health/live").json() == {"status": "ok"}
    assert website.get("/openapi.json").status_code == 200
    assert website.get("/docs").status_code == 200
    for path in ("/assets/missing.js", "/api/v1/missing", "/.env", "/missing", "/%2e%2e/.env"):
        assert website.get(path).status_code == 404


def test_api_only_mode_when_frontend_not_built(tmp_path):
    app = FastAPI()
    mount_website(app, tmp_path)
    assert TestClient(app).get("/").status_code == 404


def test_tile_proxy_uses_fixed_provider_without_browser_credentials(website, monkeypatch):
    async def get(_client, url):
        assert url == (
            "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/1/0/1"
        )
        return httpx.Response(200, content=b"tile", headers={"content-type": "image/jpeg"},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    response = website.get("/basemap/imagery/1/0/1?token=must-not-forward",
                           headers={"Authorization": "Bearer must-not-forward"})
    assert response.status_code == 200
    assert response.content == b"tile"
    assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("path", ["imagery/24/0/0", "imagery/1/0/2", "reference/1/-1/0"])
def test_invalid_tile_coordinates_rejected(website, path):
    assert website.get(f"/basemap/{path}").status_code == 404


def test_tile_provider_failure_is_sanitized(website, monkeypatch):
    async def get(_client, url):
        raise httpx.ConnectError("private provider error")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    response = website.get("/basemap/imagery/0/0/0")
    assert response.status_code == 502
    assert response.json() == {"detail": "Basemap provider unavailable"}
