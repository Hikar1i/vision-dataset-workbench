import pytest
from cryptography.fernet import Fernet

from vision_dataset_workbench.security.credentials import (
    CredentialCipher,
    CredentialEncryptionUnavailable,
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
