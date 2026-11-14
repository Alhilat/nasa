"""Hash-verified study inputs, immutable filesystem artifacts and optional DB registration."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from firescope_pipeline.ingest import inspect_csv


def read_study(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records, provenance, seen = [], [], set()
    for item in manifest["files"]:
        path = (manifest_path.parent / item["path"]).resolve()
        if not path.is_relative_to(manifest_path.parent):
            raise ValueError("Study input paths must stay inside the manifest directory")
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != item["sha256"]:
            raise ValueError("Study input checksum differs from its manifest")
        if item["processing_level"] != "standard":
            raise ValueError("Historical calibration requires standard products, not NRT mixtures")
        batch = inspect_csv(content, item["sensor"], item["product_version"], processing_level="standard")
        if batch.report["invalid_rows"]:
            raise ValueError("Study contains invalid source rows; inspect ingestion quality reports")
        for row in batch.selected:
            raw = batch.raw[row["source_row"] - 1]["raw_properties"]
            key = json.dumps([row["sensor_code"], raw, item["processing_level"]], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            records.append({**row, "source_sha256": digest,
                            "product_version": raw.get("version", item["product_version"])})
        provenance.append({key: item[key] for key in (
            "path", "sha256", "sensor", "product_version", "processing_level", "source_url",
        )} | {"observed_versions": batch.report["observed_product_versions"],
             "raw_rows": batch.report["source_rows"]})
    if not records:
        raise ValueError("Study manifest contains no valid observations")
    return pd.DataFrame(records), provenance


def code_hash():
    from app import schemas
    directory = Path(__file__).parent.parent
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*.py")):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    digest.update(b"backend/app/schemas.py")
    digest.update(Path(schemas.__file__).read_bytes())
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def register_bundle(factory, bundle_path):
    """Register only verified results from an analysis bundle; never overwrite source detections."""
    from sqlalchemy.dialects.postgresql import insert

    from app.models import AnalyticalResult, CalibrationModel
    from firescope_pipeline.jobs import run_job

    folder = Path(bundle_path)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["artifacts"].items():
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Analysis bundle artifact checksum/path verification failed")
    report = json.loads((folder / "evaluation.json").read_text(encoding="utf-8"))
    from firescope_pipeline.calibration.models import fingerprint
    for model in report["models"].values():
        if fingerprint({key: value for key, value in model.items() if key != "model_version"}) != model["model_version"]:
            raise ValueError("Calibration model content does not match its version hash")
    parameters = {"bundle_sha256": hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest(),
                  "study_id": manifest["study_id"], "protocol": report["protocol"]}

    def operation(session, job_id):
        for method, model in report["models"].items():
            supported = report["operational_calibration_supported"] and method == report["operational_method"]
            session.execute(insert(CalibrationModel).values(
                model_version=model["model_version"], job_id=job_id, method=method,
                algorithm_version=model["algorithm_version"], metric=model["metric"],
                status="supported_for_scope" if supported else "candidate_only",
                artifact=model, validation=report["evaluations"][method],
                input_manifest=manifest["input_provenance"],
            ).on_conflict_do_nothing(index_elements=["model_version"]))
        session.add(AnalyticalResult(
            job_id=job_id, result_type="sensor_harmonization_evaluation",
            method_version="sensor-calibration-v1", parameters=parameters,
            result=report, uncertainty={"physical_fire_truth_validated": False,
                                        "coverage_mode": manifest["activity_audit"]["coverage_mode"]},
        ))
        return {"study_id": manifest["study_id"], "model_versions": [
            model["model_version"] for model in report["models"].values()],
                "operational_calibration_supported": report["operational_calibration_supported"]}

    return run_job(factory, "analysis", "sensor-calibration-v1", parameters, operation)
