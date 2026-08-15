from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidIssuerError, InvalidTokenError, PyJWKClient

ALGORITHMS = ["RS256"]


@dataclass(frozen=True, slots=True)
class Principal:
    sub: UUID
    scopes: frozenset[str]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


class TokenVerifier:
    def __init__(
        self,
        trusted_issuers: Mapping[str, Sequence[str]],
        audience: str | None = None,
    ) -> None:
        # issuer url -> scope prefixes this issuer is allowed to assert
        self._trusted_issuers = {
            issuer: tuple(prefixes) for issuer, prefixes in trusted_issuers.items()
        }
        self._audience = audience
        self._jwks_clients: dict[str, PyJWKClient] = {}

    def verify(self, token: str) -> Principal:
        issuer = self._unverified_issuer(token)
        if issuer not in self._trusted_issuers:
            raise InvalidIssuerError(f"Untrusted issuer: {issuer}")

        claims = jwt.decode(
            token,
            key=self._signing_key(token, issuer),
            algorithms=ALGORITHMS,
            issuer=issuer,
            audience=self._audience,
            options={
                "verify_aud": self._audience is not None,
                "require": ["exp", "iss", "sub"],
            },
        )

        return Principal(
            sub=self._parse_sub(claims),
            scopes=self._issuer_scopes(claims, issuer),
        )

    def _signing_key(self, token: str, issuer: str) -> Any:
        jwks_client = self._jwks_clients.get(issuer)
        if jwks_client is None:
            jwks_url = f"{issuer.rstrip('/')}/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url)
            self._jwks_clients[issuer] = jwks_client

        return jwks_client.get_signing_key_from_jwt(token).key

    @staticmethod
    def _unverified_issuer(token: str) -> str:
        # only used to pick the JWKS source; the final decode pins this issuer
        claims = jwt.decode(token, options={"verify_signature": False})
        issuer = claims.get("iss")
        if not isinstance(issuer, str):
            raise InvalidIssuerError("Token is missing the iss claim")
        return issuer

    @staticmethod
    def _parse_sub(claims: Mapping[str, Any]) -> UUID:
        try:
            return UUID(claims["sub"])
        except (ValueError, TypeError) as e:
            raise InvalidTokenError("sub claim must be a UUID") from e

    def _issuer_scopes(self, claims: Mapping[str, Any], issuer: str) -> frozenset[str]:
        scopes = claims.get("scopes", [])

        if isinstance(scopes, str):
            scopes = scopes.split()
        if not isinstance(scopes, list):
            raise InvalidTokenError("scopes claim must be a list or a string")

        allowed_prefixes = self._trusted_issuers[issuer]
        return frozenset(
            scope
            for scope in scopes
            if isinstance(scope, str) and scope.startswith(allowed_prefixes)
        )
