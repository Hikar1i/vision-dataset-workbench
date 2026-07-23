import hashlib
import hmac
import secrets
from dataclasses import dataclass


class InvalidSetupToken(ValueError):
    pass


@dataclass
class SetupToken:
    plaintext: str
    _digest: bytes
    _consumed: bool = False

    @classmethod
    def create(cls) -> "SetupToken":
        plaintext = secrets.token_urlsafe(32)
        return cls(plaintext=plaintext, _digest=hashlib.sha256(plaintext.encode()).digest())

    def verify(self, candidate: str) -> None:
        candidate_digest = hashlib.sha256(candidate.encode()).digest()
        if self._consumed or not hmac.compare_digest(self._digest, candidate_digest):
            raise InvalidSetupToken("invalid or consumed setup token")

    def consume(self, candidate: str) -> None:
        self.verify(candidate)
        self._consumed = True
