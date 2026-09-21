from pathlib import Path

import pytest

from vision_dataset_workbench.config import InvalidRuntimeSettings, RuntimeSettings


def test_auth_settings_default_to_multi(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("APP_MODE", raising=False)

    settings = RuntimeSettings.from_env()

    assert settings.app_mode == "multi"


def test_ytdlp_settings_are_optional_instance_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("YTDLP_PROXY", "http://proxy.test:8080")
    monkeypatch.setenv("YTDLP_COOKIE_FILE", str(tmp_path / "cookies.txt"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    settings = RuntimeSettings.from_env()

    assert settings.ytdlp_proxy == "http://proxy.test:8080"
    assert settings.ytdlp_cookie_file == tmp_path / "cookies.txt"


def test_credential_encryption_key_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("VDW_CREDENTIAL_ENCRYPTION_KEY", "deployment-key")

    assert RuntimeSettings.from_env().credential_encryption_key == "deployment-key"


def test_invalid_app_mode_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APP_MODE", "invalid")

    with pytest.raises(InvalidRuntimeSettings):
        RuntimeSettings.from_env()
