"""Validate the deployable website and expose only public release metadata."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        url = (
            values.get("src") if tag == "script" else values.get("href") if tag == "link" else None
        )
        if url and urlsplit(url).path.startswith("/assets/"):
            self.assets.add(unquote(urlsplit(url).path).lstrip("/"))


def validate_website(directory: Path = DIST) -> list[str]:
    index = directory / "index.html"
    if not index.is_file() or not index.stat().st_size:
        raise ValueError(
            "Frontend is missing. Run bash infrastructure/render-build.sh before deploy."
        )
    parser = AssetParser()
    parser.feed(index.read_text(encoding="utf-8"))
    if not any(asset.endswith(".js") for asset in parser.assets):
        raise ValueError("Frontend index must reference compiled JavaScript assets")
    root = directory.resolve()
    for asset in sorted(parser.assets):
        path = (root / asset).resolve()
        if not path.is_relative_to(root) or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Frontend asset missing or invalid: {asset}")
    return sorted(parser.assets)


def release_info(directory: Path = DIST) -> dict:
    try:
        validate_website(directory)
        frontend = "ready"
    except ValueError:
        frontend = "missing_or_invalid"
    commit = None
    try:
        candidate = json.loads((directory / "release.json").read_text(encoding="utf-8")).get(
            "commit"
        )
        if isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{40}", candidate):
            commit = candidate
    except (OSError, ValueError, AttributeError):
        pass
    return {"frontend": frontend, "commit": commit}
