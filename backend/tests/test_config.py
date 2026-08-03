from pathlib import Path

import pytest

from vision_dataset_workbench.config import InvalidRuntimeSettings, RuntimeSettings


def test_auth_settings_default_to_multi_and_closed_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("REGISTRATION_ENABLED", raising=False)

    settings = RuntimeSettings.from_env()

    assert settings.app_mode == "multi"
    assert settings.registration_enabled is False


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


@pytest.mark.parametrize("value", ["yes", "1", "enabled"])
def test_registration_boolean_is_strict(tmp_path, monkeypatch, value):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("REGISTRATION_ENABLED", value)

    with pytest.raises(InvalidRuntimeSettings):
        RuntimeSettings.from_env()


def test_single_mode_rejects_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APP_MODE", "single")
    monkeypatch.setenv("REGISTRATION_ENABLED", "true")

    with pytest.raises(InvalidRuntimeSettings):
        RuntimeSettings.from_env()
