from datetime import UTC, datetime, timedelta
from uuid import uuid7

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from statement.infra.auth import LEEWAY, TokenVerifier
from tests.utils.auth import TEST_ISSUER, TokenTestVerifier, make_token


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
    token = make_token(rsa_private_key, expires_in=-(LEEWAY + 60))

    with pytest.raises(ExpiredSignatureError):
        token_verifier.verify(token)


def test_token_expired_within_leeway_is_accepted(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(rsa_private_key, expires_in=-(LEEWAY // 2))

    token_verifier.verify(token)


def test_token_without_iat_is_rejected(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = jwt.encode(
        {
            "iss": TEST_ISSUER,
            "sub": str(uuid7()),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        rsa_private_key,
        algorithm="RS256",
    )

    with pytest.raises(MissingRequiredClaimError):
        token_verifier.verify(token)


def test_id_token_is_rejected(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(rsa_private_key, extra_claims={"token_use": "id"})

    with pytest.raises(InvalidTokenError):
        token_verifier.verify(token)


def test_access_token_use_is_accepted(
    token_verifier: TokenVerifier,
    rsa_private_key: RSAPrivateKey,
) -> None:
    token = make_token(rsa_private_key, extra_claims={"token_use": "access"})

    token_verifier.verify(token)


@pytest.mark.parametrize("prefixes", [[], [""], ["statement.", ""]])
def test_empty_scope_prefix_is_rejected(
    rsa_private_key: RSAPrivateKey,
    prefixes: list[str],
) -> None:
    with pytest.raises(ValueError):
        TokenTestVerifier(
            public_key=rsa_private_key.public_key(),
            trusted_issuers={TEST_ISSUER: prefixes},
        )


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
    verifier = TokenTestVerifier(
        public_key=rsa_private_key.public_key(),
        trusted_issuers={TEST_ISSUER: ["statement."]},
        audience="statement-api",
    )
    token = make_token(rsa_private_key, audience="another-api")

    with pytest.raises(InvalidAudienceError):
        verifier.verify(token)
