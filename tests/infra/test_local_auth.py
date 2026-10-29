import sys
from uuid import uuid7

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from statement.app.permissions import Permission
from statement.conf import settings
from statement.infra import local_auth
from tests.utils.auth import TEST_ISSUER


def to_env_pem(key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey) -> str:
    """The format .env uses: PEM on one line, newlines escaped."""
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    return pem.replace("\n", "\\n")


@pytest.fixture
def local_settings(
    rsa_private_key: RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "jwt_local_private_key", to_env_pem(rsa_private_key))
    monkeypatch.setattr(settings, "jwt_issuers", {TEST_ISSUER: ["statement."]})
    monkeypatch.setattr(settings, "jwt_audience", None)


@pytest.mark.usefixtures("local_settings")
def test_minted_admin_token_verifies_with_all_admin_scopes() -> None:
    sub = uuid7()

    principal = local_auth.build_local_verifier().verify(
        local_auth.mint_token(sub=str(sub))
    )

    assert principal.sub == sub
    assert principal.scopes == {
        p.value for p in Permission if p.value.startswith("statement.admin.")
    }


@pytest.mark.usefixtures("local_settings")
def test_customer_role_gets_no_admin_scopes() -> None:
    principal = local_auth.build_local_verifier().verify(
        local_auth.mint_token(role="customer")
    )

    assert not any(scope.startswith("statement.admin.") for scope in principal.scopes)


@pytest.mark.usefixtures("local_settings")
def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValueError):
        local_auth.mint_token(role="root")


@pytest.mark.usefixtures("local_settings")
def test_token_from_another_key_is_rejected() -> None:
    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {
            "iss": TEST_ISSUER,
            "sub": str(uuid7()),
            "scopes": [],
            "iat": 1,
            "exp": 4_000_000_000,
        },
        rogue,
        algorithm="RS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        local_auth.build_local_verifier().verify(token)


@pytest.mark.usefixtures("local_settings")
def test_audience_is_stamped_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "jwt_audience", "statement-api")

    token = local_auth.mint_token()

    claims = jwt.decode(token, options={"verify_signature": False}, audience=None)
    assert claims["aud"] == "statement-api"
    local_auth.build_local_verifier().verify(token)


@pytest.mark.usefixtures("local_settings")
def test_expired_token_is_rejected() -> None:
    token = local_auth.mint_token(expires_in=-3600)

    with pytest.raises(jwt.ExpiredSignatureError):
        local_auth.build_local_verifier().verify(token)


def test_missing_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_local_private_key", None)

    with pytest.raises(RuntimeError, match="JWT_LOCAL_PRIVATE_KEY is not set"):
        local_auth.mint_token()


def test_non_rsa_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings, "jwt_local_private_key", to_env_pem(key))

    with pytest.raises(RuntimeError, match="not an RSA private key"):
        local_auth.mint_token()


@pytest.mark.usefixtures("local_settings")
def test_no_issuers_to_mint_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_issuers", {})

    with pytest.raises(RuntimeError, match="JWT_ISSUERS is empty"):
        local_auth.mint_token()


@pytest.mark.usefixtures("local_settings")
def test_cli_prints_a_verifiable_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sub = uuid7()
    monkeypatch.setattr(sys, "argv", ["statement-token", "--sub", str(sub)])

    local_auth.main()

    token = capsys.readouterr().out.strip()
    assert local_auth.build_local_verifier().verify(token).sub == sub
