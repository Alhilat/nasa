"""Reproducible download of official Jordan country CSVs; no fabricated gaps or secret URLs."""
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from shapely.geometry import box, mapping, shape

from firescope_pipeline.calibration.io import write_json
from firescope_pipeline.ingest import MAX_FILE_BYTES, inspect_csv

COUNTRY_ROOT = "https://firms.modaps.eosdis.nasa.gov/data/country"
BOUNDARY_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"


def _download(client, url):
    for attempt in range(3):
        try:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_FILE_BYTES:
                        raise ValueError("Public source exceeds the 50 MiB limit")
                return bytes(content)
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code not in {429, 500, 502, 503, 504}:
                raise ValueError("Official public download returned a permanent HTTP error") from None
            if attempt == 2:
                raise ValueError("Official public download failed after three attempts") from None
            time.sleep(min(2 ** attempt, 4))


def prepare_jordan(output, start_year=2013, end_year=2025, include_levant=False):
    if not 2013 <= start_year <= end_year <= 2025:
        raise ValueError("Jordan starter uses complete overlapping years 2013–2025")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    previous_path = output / "sources.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {"files": []}
    cached = {item["path"]: item for item in previous["files"]}
    files = []
    countries = ("Jordan", "Syria", "Lebanon") if include_levant else ("Jordan",)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        listing = _download(client, COUNTRY_ROOT + "/yearly_summary_files.txt").decode("utf-8")
        available = {line.split(",")[0] for line in listing.splitlines()}
        for year in range(start_year, end_year + 1):
            for product, sensor, country_name in [
                (product, sensor, country_name)
                for product, sensor in (("modis", "MODIS"), ("viirs-snpp", "VIIRS_SNPP"))
                for country_name in countries]:
                name = f"{product}_{year}_{country_name}.csv"
                if name not in available:
                    raise ValueError("Requested source is absent from NASA's official file manifest")
                path, url = output / name, f"{COUNTRY_ROOT}/{product}/{year}/{name}"
                if name in cached and path.exists():
                    content = path.read_bytes()
                    if hashlib.sha256(content).hexdigest() != cached[name]["sha256"]:
                        raise ValueError("Cached original source checksum changed")
                    retrieved = cached[name]["retrieved_at"]
                else:
                    content = _download(client, url)
                    path.write_bytes(content)
                    retrieved = datetime.now(UTC).isoformat()
                    time.sleep(1)
                batch = inspect_csv(content, sensor, "native", processing_level="standard")
                if batch.report["invalid_rows"]:
                    raise ValueError("An official source failed strict native-field validation")
                files.append({"path": name, "sensor": sensor, "product_version": "native",
                              "processing_level": "standard", "source_url": url,
                              "sha256": hashlib.sha256(content).hexdigest(), "retrieved_at": retrieved,
                              "versions": batch.report["observed_product_versions"]})
        boundary_path = output / "natural-earth-countries.geojson"
        if boundary_path.exists():
            boundary_bytes = boundary_path.read_bytes()
        else:
            boundary_bytes = _download(client, BOUNDARY_URL)
            boundary_path.write_bytes(boundary_bytes)
    countries_data = json.loads(boundary_bytes)["features"]
    country = next(feature for feature in countries_data
                   if feature["properties"].get("ADM0_A3") == "JOR")
    geometry = shape(country["geometry"])
    west, south, east, north = geometry.bounds
    midx, midy = (west + east) / 2, (south + north) / 2
    features = []
    for name, bounds in (("northwest", (west, midy, midx, north)), ("northeast", (midx, midy, east, north)),
                         ("southwest", (west, south, midx, midy)), ("southeast", (midx, south, east, midy))):
        features.append({"type": "Feature", "properties": {"region_id": "JOR_" + name,
                         "label": "Jordan study block " + name},
                         "geometry": mapping(geometry.intersection(box(*bounds)))})
    if include_levant:
        features = [{"type": "Feature", "properties": {"region_id": code, "label": label},
                     "geometry": next(feature["geometry"] for feature in countries_data
                                      if feature["properties"].get("ADM0_A3") == code)}
                    for code, label in (("JOR", "Jordan"), ("SYR", "Syria"), ("LBN", "Lebanon"))]
    write_json(output / "regions.geojson", {"type": "FeatureCollection", "features": features,
        "metadata": {"source_url": BOUNDARY_URL, "source_sha256": hashlib.sha256(boundary_bytes).hexdigest(),
                     "boundary_scale": "1:110m", "region_method": "country polygons" if include_levant
                     else "country clipped at bounding-box midlines; not administrative regions"}})
    write_json(output / "sources.json", {"files": files})
    return {"files": len(files), "output": str(output.resolve())}
