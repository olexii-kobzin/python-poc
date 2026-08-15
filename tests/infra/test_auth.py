from uuid import uuid7

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)

from statement.infra.auth import TokenVerifier
from tests.utils.auth import TEST_ISSUER, TestKeyVerifier, make_token


def test_valid_token(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    sub = uuid7()
    token = make_token(
        rsa_private_key,
        sub=str(sub),
        scopes=["statement.admin.accounts.create"],
    )

    principal = token_verifier.verify(token)

    assert principal.sub == sub
    assert principal.scopes == {"statement.admin.accounts.create"}


def test_expired_token(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(rsa_private_key, expires_in=-10)

    with pytest.raises(ExpiredSignatureError):
        token_verifier.verify(token)


def test_token_signed_with_wrong_key(token_verifier: TokenVerifier) -> None:
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(rogue_key, scopes=["statement.admin.accounts.create"])

    with pytest.raises(InvalidSignatureError):
        token_verifier.verify(token)


def test_untrusted_issuer(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(rsa_private_key, issuer="https://rogue.test")

    with pytest.raises(InvalidIssuerError):
        token_verifier.verify(token)


def test_scopes_outside_issuer_prefix_are_dropped(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(
        rsa_private_key,
        scopes=["statement.admin.accounts.create", "other-service.admin"],
    )

    principal = token_verifier.verify(token)

    assert principal.scopes == {"statement.admin.accounts.create"}


def test_non_uuid_sub(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(rsa_private_key, sub="not-a-uuid")

    with pytest.raises(InvalidTokenError):
        token_verifier.verify(token)


def test_audience_mismatch(rsa_private_key: RSAPrivateKey) -> None:
    verifier = TestKeyVerifier(
        public_key=rsa_private_key.public_key(),
        trusted_issuers={TEST_ISSUER: ["statement."]},
        audience="statement-api",
    )
    token = make_token(rsa_private_key, audience="another-api")

    with pytest.raises(InvalidAudienceError):
        verifier.verify(token)
