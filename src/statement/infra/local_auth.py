"""Local-only auth helpers: mint and verify JWTs with a fixed dev keypair.

This exists so you can authenticate against a locally running API (e.g. from
Apidog) without Cognito. A single RSA private key lives in the environment as
``JWT_LOCAL_PRIVATE_KEY``; the CLI here mints tokens signed with it, and
``build_local_verifier`` trusts the matching public key directly instead of
fetching a JWKS. Never wire any of this up outside ``AppEnv.LOCAL``.
"""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid7

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from statement.app.permissions import Permission
from statement.conf import settings
from statement.infra.auth import ALGORITHMS, TokenVerifier

class UserRole(StrEnum):
    ADMIN = "admin"
    CUSTOMER = "customer"

def _load_private_key() -> RSAPrivateKey:
    pem = settings.jwt_local_private_key
    if not pem:
        raise RuntimeError(
            "JWT_LOCAL_PRIVATE_KEY is not set; local auth is unavailable"
        )
    # .env stores the PEM on one line with escaped newlines
    key = serialization.load_pem_private_key(
        pem.replace("\\n", "\n").encode(), password=None
    )
    if not isinstance(key, RSAPrivateKey):
        raise RuntimeError("JWT_LOCAL_PRIVATE_KEY is not an RSA private key")
    return key


class LocalKeyVerifier(TokenVerifier):
    """TokenVerifier that trusts a fixed public key instead of fetching JWKS."""

    def __init__(self, public_key: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._public_key = public_key

    def _signing_key(self, token: str, issuer: str) -> Any:
        return self._public_key


def build_local_verifier() -> LocalKeyVerifier:
    return LocalKeyVerifier(
        public_key=_load_private_key().public_key(),
        trusted_issuers=settings.jwt_issuers,
        audience=settings.jwt_audience,
    )


def _default_issuer() -> str:
    try:
        return next(iter(settings.jwt_issuers))
    except StopIteration as e:
        raise RuntimeError("JWT_ISSUERS is empty; nothing to mint for") from e


def mint_token(
    *,
    sub: str | None = None,
    role: str | None = None,
    issuer: str | None = None,
    expires_in: int = 3600 * 6,
) -> str:
    now = datetime.now(UTC)
    role = UserRole(role) if role is not None else UserRole.ADMIN
    scopes = [
        p.value for p in Permission if p.value.startswith(f"statement.{role.value}.")
    ]

    claims: dict[str, Any] = {
        "iss": issuer or _default_issuer(),
        "sub": sub if sub is not None else str(uuid7()),
        "scopes": scopes,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    if settings.jwt_audience is not None:
        claims["aud"] = settings.jwt_audience

    return jwt.encode(claims, _load_private_key(), algorithm=ALGORITHMS[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mint a local dev JWT for the statement API (no Cognito)."
    )
    parser.add_argument(
        "--sub",
        default=None,
        help="subject UUID (default: a fresh uuid7)",
    )
    parser.add_argument(
        "--role",
        default=None,
        choices=list(UserRole),
        help="assign a role",
    )
    parser.add_argument(
        "--issuer",
        default=None,
        help="override the iss claim (default: first JWT_ISSUERS)",
    )
    parser.add_argument(
        "--ttl", type=int, default=3600, help="lifetime in seconds (default: 3600)"
    )
    args = parser.parse_args()

    print(
        mint_token(
            sub=args.sub,
            role=args.role,
            issuer=args.issuer,
            expires_in=args.ttl,
        )
    )


if __name__ == "__main__":
    main()
