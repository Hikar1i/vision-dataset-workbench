import pytest
from cryptography.fernet import Fernet

from vision_dataset_workbench.security.credentials import (
    CredentialCipher,
    CredentialEncryptionUnavailable,
    mask_credential,
    resolve_credential_key,
)


def test_credentials_are_encrypted_and_require_the_deployment_key():
    cipher = CredentialCipher(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("secret-token")

    assert encrypted != "secret-token"
    assert cipher.decrypt(encrypted) == "secret-token"
    with pytest.raises(CredentialEncryptionUnavailable, match="not configured"):
        CredentialCipher(None)
    with pytest.raises(CredentialEncryptionUnavailable, match="cannot be decrypted"):
        CredentialCipher(Fernet.generate_key().decode()).decrypt(encrypted)


def test_workspace_credential_key_is_created_once(tmp_path):
    workspace = tmp_path / "workspace"

    first = resolve_credential_key(None, workspace)
    second = resolve_credential_key(None, workspace)
    key_path = workspace / "config/credential.key"

    assert first == second
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert mask_credential("sk-524sd123456789456d") == "sk-524sd******456d"


def test_configured_credential_key_takes_priority(tmp_path):
    configured = Fernet.generate_key().decode()

    assert resolve_credential_key(configured, tmp_path / "workspace") == configured
    assert not (tmp_path / "workspace/config/credential.key").exists()
