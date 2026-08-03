from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User, UserXAnyLabelingSetting
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.xanylabeling import (
    RemoteModelOption,
    XAnyLabelingUnavailable,
)

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


class FakeClient:
    calls = []

    def __init__(self, server_url, api_key):
        self.server_url = server_url
        self.api_key = api_key

    def list_models(self):
        self.calls.append((self.server_url, self.api_key))
        if "unavailable" in self.server_url:
            raise XAnyLabelingUnavailable("server unavailable")
        return [
            RemoteModelOption(
                '["detector",null]', "detector", None, "Detector", "default"
            )
        ]


def make_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects").mkdir(parents=True)
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id="user-a",
                    username="user-a",
                    username_normalized="user-a",
                    password_hash=password_hash,
                    status="active",
                ),
                User(
                    id="user-b",
                    username="user-b",
                    username_normalized="user-b",
                    password_hash=password_hash,
                    status="active",
                ),
            ]
        )
        session.commit()
    engine.dispose()
    settings = RuntimeSettings(
        home=home,
        workspace=workspace,
        credential_encryption_key=Fernet.generate_key().decode(),
    )
    app = create_app(settings)
    app.state.xanylabeling_settings_service.client_factory = FakeClient
    return app


def client_for(app, username):
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    ).status_code == 200
    return client


def test_settings_are_verified_encrypted_and_isolated_per_user(tmp_path):
    FakeClient.calls.clear()
    app = make_app(tmp_path)
    user_a = client_for(app, "user-a")
    user_b = client_for(app, "user-b")
    url = "/api/v1/me/x-anylabeling-server"

    assert user_a.get(url).json() == {
        "configured": False,
        "server_url": "",
        "has_api_key": False,
        "available": False,
    }
    assert user_a.put(
        url,
        json={
            "server_url": "http://server.test",
            "api_key_mode": "replace",
            "api_key": "secret-token",
        },
    ).status_code == 403
    saved = user_a.put(
        url,
        headers=ORIGIN,
        json={
            "server_url": "http://server.test/",
            "api_key_mode": "replace",
            "api_key": "secret-token",
        },
    )

    assert saved.status_code == 200
    assert saved.json()["setting"]["server_url"] == "http://server.test"
    assert saved.json()["models"][0]["model_id"] == "detector"
    assert "secret-token" not in saved.text
    assert user_a.get(url).json()["has_api_key"] is True
    assert user_b.get(url).json()["configured"] is False
    with Session(app.state.auth_service.engine) as session:
        record = session.get(UserXAnyLabelingSetting, "user-a")
        assert record.api_key_ciphertext != "secret-token"

    refreshed = user_a.get(f"{url}/models")
    assert refreshed.status_code == 200
    assert FakeClient.calls[-1] == ("http://server.test", "secret-token")


def test_failed_validation_keeps_previous_setting(tmp_path):
    app = make_app(tmp_path)
    client = client_for(app, "user-a")
    url = "/api/v1/me/x-anylabeling-server"
    assert client.put(
        url,
        headers=ORIGIN,
        json={"server_url": "http://server.test", "api_key_mode": "clear"},
    ).status_code == 200

    failed = client.put(
        url,
        headers=ORIGIN,
        json={"server_url": "http://unavailable.test", "api_key_mode": "retain"},
    )

    assert failed.status_code == 503
    assert client.get(url).json()["server_url"] == "http://server.test"
