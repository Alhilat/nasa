"""Download and import NASA's annual Jordan country files, retaining a local ledger."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from app.db import session_factory
from dotenv import load_dotenv

from firescope_pipeline.calibration.prepare import COUNTRY_ROOT, _download
from firescope_pipeline.ingest import inspect_csv
from firescope_pipeline.service import import_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output", default="data/jordan-archive")
    args = parser.parse_args()
    if not 2000 <= args.start_year <= args.end_year <= datetime.now(UTC).year:
        parser.error("Invalid year range")
    load_dotenv(".env")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    ledger_path = output / "ledger.json"
    ledger = (json.loads(ledger_path.read_text(encoding="utf-8"))
              if ledger_path.exists() else {"files": {}})

    def save():
        tmp = ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        tmp.replace(ledger_path)

    with httpx.Client(timeout=60, follow_redirects=False) as client:
        catalog = _download(client, COUNTRY_ROOT + "/yearly_summary_files.txt")
        names = {line.split(",")[0] for line in catalog.decode("utf-8").splitlines()}
        ledger["catalog"] = {"url": COUNTRY_ROOT + "/yearly_summary_files.txt",
                             "retrieved_at": datetime.now(UTC).isoformat(),
                             "sha256": hashlib.sha256(catalog).hexdigest()}
        (output / "yearly_summary_files.txt").write_bytes(catalog)
        products = (("modis", "MODIS", 2000), ("viirs-snpp", "VIIRS_SNPP", 2012))
        for product, sensor, first in products:
            for year in range(max(first, args.start_year), args.end_year + 1):
                name = f"{product}_{year}_Jordan.csv"
                url = f"{COUNTRY_ROOT}/{product}/{year}/{name}"
                if name not in names:
                    ledger["files"].setdefault(
                        name, {"status": "absent_from_catalog", "source_url": url})
                    save()
                    continue
                path = output / name
                previous = ledger["files"].get(name, {})
                if path.exists() and previous.get("sha256"):
                    content = path.read_bytes()
                    if hashlib.sha256(content).hexdigest() != previous["sha256"]:
                        raise ValueError(f"Cached file checksum mismatch: {name}")
                    retrieved = datetime.fromisoformat(previous["retrieved_at"])
                else:
                    content = _download(client, url)
                    retrieved = datetime.now(UTC)
                    path.write_bytes(content)
                report = inspect_csv(content, sensor, "native", processing_level="standard").report
                entry = {"source_url": url, "retrieved_at": retrieved.isoformat(),
                         "sha256": hashlib.sha256(content).hexdigest(), "sensor": sensor,
                         "versions": report["observed_product_versions"],
                         "quality": report, "status": "downloaded"}
                ledger["files"][name] = entry
                save()
                result = import_source(session_factory(), content, filename=name, sensor=sensor,
                                       product_version="native", processing_level="standard",
                                       source_url=url, retrieved_at=retrieved)
                entry["status"] = "imported"
                entry["import_result"] = result
                save()
                print(f"Imported {name}", flush=True)


if __name__ == "__main__":
    main()
