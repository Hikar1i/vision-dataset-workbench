from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionUnavailable(ValueError):
    pass


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
