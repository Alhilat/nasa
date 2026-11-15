"""Serve the built website and its fixed public basemap providers with the API."""

from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from app.release import validate_website

router = APIRouter()
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
PAGE_PATHS = {".", "", "explorer", "history", "sources", "methodology"}


class WebsiteFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and path.rstrip("/") in PAGE_PATHS:
                response = await super().get_response("index.html", scope)
                response.headers["Cache-Control"] = "no-cache"
                return response
            raise


def mount_website(app: FastAPI, directory: Path = FRONTEND_DIST, *, required: bool = False):
    """Mount last, so the API and documentation retain their own routes."""
    if required:
        validate_website(directory)
    if (directory / "index.html").is_file():
        app.mount("/", WebsiteFiles(directory=directory), name="website")


@router.get("/basemap/{layer}/{z}/{y}/{x}", include_in_schema=False)
async def basemap(layer: Literal["imagery", "reference"], z: int, y: int, x: int):
    if not (0 <= z <= 23 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(404, "Tile not found")
    service = "World_Imagery" if layer == "imagery" else "Reference/World_Boundaries_and_Places"
    url = f"https://services.arcgisonline.com/ArcGIS/rest/services/{service}/MapServer/tile/{z}/{y}/{x}"
    try:
        # A new request forwards no browser cookies, authorization, or query string.
        async with httpx.AsyncClient(timeout=15) as client:
            tile = await client.get(url)
        if tile.status_code == 404:
            raise HTTPException(404, "Tile not found")
        tile.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Basemap provider unavailable") from exc
    content_type = tile.headers.get("content-type", "").split(";", 1)[0]
    if not content_type.startswith("image/"):
        raise HTTPException(502, "Invalid basemap response")
    return Response(tile.content, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"})
