import pytest
from app.core.config import PROJECT_ENV_FILE, Settings
from pydantic import ValidationError


def test_settings_use_project_env_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings.model_config["env_file"] == PROJECT_ENV_FILE
    project_env = tmp_path / "project.env"
    project_env.write_text("DATABASE_URL=postgresql://project-database\n")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / ".env").write_text("DATABASE_URL=postgresql://wrong-database\n")
    monkeypatch.setitem(Settings.model_config, "env_file", project_env)
    monkeypatch.chdir(other_dir)
    assert Settings().database_url == "postgresql://project-database"


def test_database_url_is_required_when_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)
