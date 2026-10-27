from pathlib import Path

from vision_dataset_workbench.config import RuntimeSettings


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
