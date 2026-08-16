from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid7

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Security, status, Query
from pgqueuer import Queries
from sqlalchemy.ext.asyncio import AsyncSession

from statement import fast_deps
from statement.app.permissions import Permission
from statement.app.repository import CustomerAccountReadRepository
from statement.app.schemas.account import CustomerAccountCreate, CustomerAccountUpdate, CustomerAccountDisplay, \
    CustomerAccountListQuery, LedgerDiscrepancyDisplay, LedgerDiscrepancyResolve
from statement.app.events.local.main import CustomerAccountCreated
from statement.app.schemas.response import PaginatedResponse, PaginatedResponseMeta
from statement.domain.entities import CustomerAccount
from statement.domain.entities.account import (
    CustomerAccountLedger,
    CustomerAccountStatus,
)
from statement.domain.repository import CustomerAccountRepository
from statement.infra.auth import Principal
from statement.infra.models.account import LedgerDiscrepancyKind
from statement.infra.repository.ledger_verification import (
    CustomerAccountLedgerVerificationRepositoryImpl,
)

router = APIRouter(prefix="/v1")
log = structlog.get_logger(__name__)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_customer_account(
    account_create: Annotated[CustomerAccountCreate, Body()],
    session: Annotated[AsyncSession, Depends(fast_deps.get_session)],
    queries: Annotated[Queries, Depends(fast_deps.get_pgqueuer_queries)],
    principal: Annotated[
        Principal,
        Security(fast_deps.get_principal, scopes=[Permission.ADMIN_ACCOUNTS_CREATE]),
    ],
) -> None:
    account = CustomerAccount.create(
        entity_id=uuid7(),
        customer_id=account_create.customer_id,
        currency=account_create.currency,
        name=account_create.name,
        updated_by=principal.sub,
    )

    session.add(account)
    session.add(
        CustomerAccountLedger.create(
            entity_id=account.id,
            created_by=principal.sub,
        )
    )

    event = CustomerAccountCreated(
        id=account.id,
        customer_id=account.customer_id,
        currency=account.currency,
        name=account.name,
        status=account.status,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )

    await queries.enqueue(
        entrypoint=event.route(),
        payload=event.to_payload_bytes(),
        dedupe_key=event.dedupe_key()
    )

    await session.commit()


@router.patch("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def updated_customer_account(
    account_id: Annotated[UUID, Path()],
    account_update: Annotated[CustomerAccountUpdate, Body()],
    session: Annotated[AsyncSession, Depends(fast_deps.get_session)],
    repo: Annotated[
        CustomerAccountRepository,
        Depends(fast_deps.get_customer_account_repo),
    ],
    principal: Annotated[
        Principal,
        Security(fast_deps.get_principal, scopes=[Permission.ADMIN_ACCOUNTS_UPDATE]),
    ],
) -> None:
    account = await repo.find_by_id(account_id)
    if account is None or account.status == CustomerAccountStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if account_update.name is not None:
        account.name = account_update.name
    if account_update.status is not None:
        account.status = account_update.status
    account.updated_by = principal.sub

    await session.commit()


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_account(
    account_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(fast_deps.get_session)],
    repo: Annotated[
        CustomerAccountRepository,
        Depends(fast_deps.get_customer_account_repo),
    ],
    principal: Annotated[
        Principal,
        Security(fast_deps.get_principal, scopes=[Permission.ADMIN_ACCOUNTS_DELETE]),
    ],
) -> None:
    account = await repo.find_by_id(account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    account.status = CustomerAccountStatus.DELETED
    account.updated_by = principal.sub

    await session.commit()


@router.get("/accounts")
async def get_accounts(
    query: Annotated[CustomerAccountListQuery, Query()],
    repo: Annotated[
        CustomerAccountReadRepository,
        Depends(fast_deps.get_customer_account_read_repo),
    ],
    principal: Annotated[
        Principal,
        Security(fast_deps.get_principal, scopes=[Permission.ADMIN_ACCOUNTS_GET]),
    ],
) -> PaginatedResponse[CustomerAccountDisplay]:
    accounts, cursor = await repo.list_all(query)

    return PaginatedResponse(
        data=accounts,
        meta=PaginatedResponseMeta(
            next_cursor=cursor.encode() if cursor is not None else None,
        ),
    )


@router.get("/accounts/{id}/ledger/discrepancy")
async def get_customer_account_ledger_discrepancy(
    id: Annotated[UUID, Path()],
    repo: Annotated[
        CustomerAccountLedgerVerificationRepositoryImpl,
        Depends(fast_deps.get_ledger_verification_repo),
    ],
    principal: Annotated[
        Principal,
        Security(
            fast_deps.get_principal,
            scopes=[Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET],
        ),
    ],
) -> LedgerDiscrepancyDisplay:
    discrepancy = await repo.find_open_discrepancy(id)
    if discrepancy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No open ledger discrepancy for this account",
        )

    checkpoint = await repo.find_latest_checkpoint(id)

    return LedgerDiscrepancyDisplay(
        id=discrepancy.account_id,
        no=discrepancy.no,
        kind=LedgerDiscrepancyKind(discrepancy.kind),
        prev_no=discrepancy.prev_no,
        expected_balance=discrepancy.expected_balance,
        actual_balance=discrepancy.actual_balance,
        detected_at=discrepancy.detected_at,
        verified_through_no=checkpoint.through_no if checkpoint else 0,
    )


@router.post(
    "/accounts/{id}/ledger/discrepancy/resolve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def resolve_customer_account_ledger_discrepancy(
    id: Annotated[UUID, Path()],
    resolution: Annotated[LedgerDiscrepancyResolve, Body()],
    session: Annotated[AsyncSession, Depends(fast_deps.get_session)],
    repo: Annotated[
        CustomerAccountLedgerVerificationRepositoryImpl,
        Depends(fast_deps.get_ledger_verification_repo),
    ],
    principal: Annotated[
        Principal,
        Security(
            fast_deps.get_principal,
            scopes=[Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE],
        ),
    ],
) -> None:
    """Force a checkpoint past a break and lift the account's quarantine.

    Repairs nothing: it records that the current rows were reviewed and are the
    truth to carry forward. The old checkpoint stays in the verified table --
    it is insert-only, so the superseded row is the record of what was believed
    before, which is exactly what you want when auditing the incident later.
    """
    discrepancy = await repo.find_open_discrepancy(id)
    if discrepancy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No open ledger discrepancy for this account",
        )

    checkpoint = await repo.find_latest_checkpoint(id)
    anchor_no = checkpoint.through_no if checkpoint else 0

    # for a gap or a balance break, the broken row is the narrowest thing to
    # accept; for an anchor_balance break it *is* the anchor, so accepting it
    # would not move anything and the caller has to say how far to trust
    through_no = resolution.through_no or (
        None
        if discrepancy.kind == LedgerDiscrepancyKind.ANCHOR_BALANCE
        else discrepancy.no
    )
    if through_no is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "through_no is required for an anchor_balance discrepancy: "
                "the break is on the row that is already checkpointed"
            ),
        )

    if through_no <= anchor_no:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"through_no must be greater than {anchor_no}",
        )

    balance = await repo.find_ledger_balance(id, through_no)
    if balance is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No ledger row {through_no} for this account",
        )

    repo.add_checkpoint(account_id=id, through_no=through_no, balance=balance)
    discrepancy.resolved_at = datetime.now(UTC)
    discrepancy.resolved_by = principal.sub

    await session.commit()
    log.warning(
        "customer_account_ledger.discrepancy.resolved",
        details={
            "account_id": str(id),
            "kind": discrepancy.kind,
            "no": discrepancy.no,
            "accepted_through_no": through_no,
            "accepted_balance": str(balance),
            "resolved_by": str(principal.sub),
        },
    )
