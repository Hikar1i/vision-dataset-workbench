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
