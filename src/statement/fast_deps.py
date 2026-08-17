from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from jwt import InvalidTokenError
from pgqueuer import Queries
from sqlalchemy.ext.asyncio import AsyncSession

from statement import deps
from statement.app.auth import Principal
from statement.app.repository import (
    CustomerAccountLedgerVerificationRepository,
    CustomerAccountReadRepository,
)
from statement.conf import AppEnv, settings
from statement.domain.repository import CustomerAccountRepository
from statement.infra.auth import TokenVerifier
from statement.read.repository.account import CustomerAccountReadRepositoryImpl

get_session = deps.get_session

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_token_verifier() -> TokenVerifier:
    # local dev: trust a fixed keypair so you can auth without Cognito/JWKS
    if settings.app_env == AppEnv.LOCAL and settings.jwt_local_private_key:
        from statement.infra.local_auth import build_local_verifier

        return build_local_verifier()

    return TokenVerifier(
        trusted_issuers=settings.jwt_issuers,
        audience=settings.jwt_audience,
    )


# sync on purpose: FastAPI runs it in the threadpool, so the blocking
# JWKS fetch inside PyJWKClient never stalls the event loop
def get_principal(
    security_scopes: SecurityScopes,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> Principal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        principal = verifier.verify(credentials.credentials)
    except InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    missing = [
        scope for scope in security_scopes.scopes if not principal.has_scope(scope)
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permissions: {', '.join(missing)}",
        )

    return principal


async def get_pgqueuer_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Queries:
    connection = await session.connection()
    return await deps.make_queries(connection)


async def get_customer_account_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomerAccountRepository:
    return deps.get_customer_account_repo(session)


async def get_ledger_verification_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomerAccountLedgerVerificationRepository:
    return deps.get_ledger_verification_repo(session)


async def get_customer_account_read_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomerAccountReadRepository:
    return CustomerAccountReadRepositoryImpl(session)
