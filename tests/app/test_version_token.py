from uuid import uuid7

import pytest

from statement.app import version_token
from statement.conf import settings


def test_token_length_is_fixed_regardless_of_version() -> None:
    """The schema constrains the field to exactly TOKEN_LENGTH."""
    account_id = uuid7()

    assert len(version_token.issue(account_id, 1)) == version_token.TOKEN_LENGTH
    assert len(version_token.issue(account_id, 10**9)) == version_token.TOKEN_LENGTH


def test_issue_is_deterministic() -> None:
    """verify() re-issues and compares, so the same inputs must agree."""
    account_id = uuid7()

    assert version_token.issue(account_id, 3) == version_token.issue(account_id, 3)


def test_verify_accepts_the_issued_token() -> None:
    account_id = uuid7()

    assert version_token.verify(account_id, 3, version_token.issue(account_id, 3))


def test_verify_rejects_a_bumped_version() -> None:
    """The whole point: someone else wrote, so the client's token is stale."""
    account_id = uuid7()
    token = version_token.issue(account_id, 3)

    assert not version_token.verify(account_id, 4, token)


def test_verify_rejects_a_token_issued_for_another_entity() -> None:
    """Signing over the id stops a token being replayed across accounts."""
    token = version_token.issue(uuid7(), 3)

    assert not version_token.verify(uuid7(), 3, token)


def test_verify_rejects_a_tampered_token() -> None:
    account_id = uuid7()
    token = version_token.issue(account_id, 3)
    tampered = ("a" if token[0] != "a" else "b") + token[1:]

    assert not version_token.verify(account_id, 3, tampered)


def test_verify_rejects_a_token_signed_with_another_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotating the secret invalidates every token clients are holding."""
    account_id = uuid7()
    token = version_token.issue(account_id, 3)

    monkeypatch.setattr(settings, "version_token_secret", "a-different-secret")

    assert not version_token.verify(account_id, 3, token)
