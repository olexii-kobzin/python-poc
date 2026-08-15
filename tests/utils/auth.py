from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Optional, Protocol
from uuid import uuid7

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from statement.infra.auth import TokenVerifier

TEST_ISSUER = "https://issuer.test"


class AuthHeaders(Protocol):
    def __call__(
        self,
        scopes: Sequence[str],
        sub: str | None = None,
    ) -> dict[str, str]: ...


class TestKeyVerifier(TokenVerifier):
    """TokenVerifier that trusts a fixed public key instead of fetching JWKS."""

    def __init__(self, public_key: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._public_key = public_key

    def _signing_key(self, token: str, issuer: str) -> Any:
        return self._public_key


def make_token(
    private_key: RSAPrivateKey,
    *,
    scopes: Sequence[str] = (),
    sub: str | None = None,
    issuer: str = TEST_ISSUER,
    expires_in: int = 300,
    audience: str | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": issuer,
        "sub": sub if sub is not None else str(uuid7()),
        "scopes": list(scopes),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    if audience is not None:
        claims["aud"] = audience

    return jwt.encode(claims, private_key, algorithm="RS256")
