import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionUnavailable(ValueError):
    pass


def resolve_credential_key(configured: str | None, workspace: Path) -> str:
    if configured:
        return configured
    directory = workspace / "config"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / "credential.key"
    if not path.exists():
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(Fernet.generate_key().decode())
    path.chmod(0o600)
    key = path.read_text().strip()
    CredentialCipher(key)
    return key


def mask_credential(value: str) -> str:
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:8]}******{value[-4:]}"


class CredentialCipher:
    def __init__(self, key: str | None):
        if not key:
            raise CredentialEncryptionUnavailable(
                "credential encryption key is not configured"
            )
        try:
            self._fernet = Fernet(key.encode())
        except (TypeError, ValueError) as exc:
            raise CredentialEncryptionUnavailable(
                "credential encryption key is invalid"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except (InvalidToken, ValueError) as exc:
            raise CredentialEncryptionUnavailable(
                "stored credential cannot be decrypted"
            ) from exc
