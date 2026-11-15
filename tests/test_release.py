import json

import pytest

from app.release import release_info, validate_website


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("/* compiled */")
    (tmp_path / "assets" / "app.css").write_text("body{}")
    (tmp_path / "index.html").write_text(
        '<link href="/assets/app.css" rel="stylesheet"><script src="/assets/app.js"></script>'
    )
    return tmp_path


def test_complete_artifact_and_public_commit(dist):
    (dist / "release.json").write_text(json.dumps({"commit": "a" * 40, "secret": "never-return"}))
    assert validate_website(dist) == ["assets/app.css", "assets/app.js"]
    assert release_info(dist) == {"frontend": "ready", "commit": "a" * 40}


def test_missing_asset_fails_the_build(dist):
    (dist / "assets" / "app.js").unlink()
    with pytest.raises(ValueError, match="asset missing"):
        validate_website(dist)
    assert release_info(dist)["frontend"] == "missing_or_invalid"


def test_missing_frontend_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="Frontend is missing"):
        validate_website(tmp_path)


def test_empty_javascript_shell_cannot_pass(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    with pytest.raises(ValueError, match="compiled JavaScript"):
        validate_website(tmp_path)


def test_asset_traversal_rejected(dist):
    (dist / "index.html").write_text('<script src="/assets/%2e%2e/%2e%2e/private.js"></script>')
    with pytest.raises(ValueError, match="invalid"):
        validate_website(dist)


@pytest.mark.parametrize("metadata", ["not json", '{"commit":"private text"}', "[]"])
def test_malformed_metadata_is_not_exposed(dist, metadata):
    (dist / "release.json").write_text(metadata)
    assert release_info(dist) == {"frontend": "ready", "commit": None}
