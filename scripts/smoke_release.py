"""Read-only verification of a combined PIRX deployment."""

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.release import AssetParser

PAGES = ("/", "/explorer", "/history", "/sources", "/methodology")


def verify(base_url, *, expected_commit=None, require_data=False, basemap=True):
    checks = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30, follow_redirects=True) as client:
        for page in PAGES:
            response = client.get(page)
            if response.status_code != 200 or "text/html" not in response.headers.get(
                "content-type", ""
            ):
                raise ValueError(f"Website route failed: {page} HTTP {response.status_code}")
            if client.head(page).status_code != 200:
                raise ValueError(f"HEAD request failed: {page}")
            checks.append(page)
        parser = AssetParser()
        parser.feed(client.get("/").text)
        if not any(path.endswith(".js") for path in parser.assets):
            raise ValueError("Website HTML has no compiled JavaScript assets")
        for asset in sorted(parser.assets):
            response = client.get("/" + asset)
            if (
                response.status_code != 200
                or not response.content
                or "text/html" in response.headers.get("content-type", "")
            ):
                raise ValueError(f"Compiled asset failed: {asset}")
            checks.append("/" + asset)
        build = client.get("/api/v1/health/build")
        if build.status_code != 200 or build.json().get("frontend") != "ready":
            raise ValueError("Combined build health check failed")
        if expected_commit and build.json().get("commit") != expected_commit:
            raise ValueError("Deployed commit does not match expected commit")
        ready = client.get("/api/v1/health/ready")
        if ready.status_code != 200 or ready.json().get("database") != "connected":
            raise ValueError("Database readiness failed")
        sources = client.get("/api/v1/sources", params={"limit": 1})
        if sources.status_code != 200 or not isinstance(sources.json().get("items"), list):
            raise ValueError("Read-only archive query failed")
        if require_data and not sources.json()["items"]:
            raise ValueError("Expected uploaded sources but the archive is empty")
        if client.get("/api/v1/missing").status_code != 404:
            raise ValueError("Unknown API route was swallowed by the frontend")
        checks.extend(["build", "database", "archive", "unknown-api-404"])
        if basemap:
            tile = client.get("/basemap/imagery/0/0/0")
            if tile.status_code != 200 or not tile.headers.get("content-type", "").startswith(
                "image/"
            ):
                raise ValueError("Public basemap tile failed")
            checks.append("basemap")
        return {"status": "passed", "commit": build.json().get("commit"), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--expect-commit")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument(
        "--skip-basemap", action="store_true", help="Skip the external provider in offline CI"
    )
    args = parser.parse_args()
    try:
        result = verify(
            args.base_url,
            expected_commit=args.expect_commit,
            require_data=args.require_data,
            basemap=not args.skip_basemap,
        )
        print(json.dumps(result, indent=2))
        return 0
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # Never emit URLs containing credentials or arbitrary server response bodies.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(json.dumps({"status": "failed", "reason": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
