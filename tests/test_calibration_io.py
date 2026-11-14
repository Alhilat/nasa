"""Synthetic, test-only source payloads; no network and no scientific observations are generated."""
import hashlib
import json

import pytest

from firescope_pipeline.calibration.io import read_study, register_bundle, write_json


def test_manifest_verifies_source_hash_and_preserves_sensor_version(tmp_path):
    content = (b"latitude,longitude,acq_date,acq_time,satellite,confidence,version\n"
               b"0,0,2024-01-01,0000,A,80,6.1\n")
    (tmp_path / "test-only.csv").write_bytes(content)
    manifest = {"files": [{"path": "test-only.csv", "sha256": hashlib.sha256(content).hexdigest(),
                           "sensor": "MODIS", "product_version": "6.1", "processing_level": "standard",
                           "source_url": "https://example.org/test-only"}]}
    path = tmp_path / "manifest.json"
    write_json(path, manifest)
    records, provenance = read_study(path)
    assert records.product_version.tolist() == ["6.1"]
    assert records.sensor_code.tolist() == ["MODIS_AQUA"]
    assert provenance[0]["raw_rows"] == 1
    (tmp_path / "test-only.csv").write_bytes(content + b"\n")
    with pytest.raises(ValueError, match="checksum"):
        read_study(path)


def test_registration_verifies_artifacts_before_database_access(tmp_path):
    (tmp_path / "evaluation.json").write_text("{}", encoding="utf-8")
    write_json(tmp_path / "manifest.json", {"artifacts": {"evaluation.json": "0" * 64}})
    with pytest.raises(ValueError, match="checksum"):
        register_bundle(None, tmp_path)
