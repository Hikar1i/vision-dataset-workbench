import pytest

from vision_dataset_workbench.setup.tokens import InvalidSetupToken, SetupToken


def test_token_verifies_then_consumes():
    token = SetupToken.create()

    token.verify(token.plaintext)
    token.consume(token.plaintext)

    with pytest.raises(InvalidSetupToken):
        token.verify(token.plaintext)


def test_wrong_token_is_rejected():
    token = SetupToken.create()

    with pytest.raises(InvalidSetupToken):
        token.verify("wrong")
