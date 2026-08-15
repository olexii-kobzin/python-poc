from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid7

import pytest
import sqlalchemy as sa
from pgqueuer import RetryRequested
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from statement.app.commands.local.main import CreatePayment
from statement.app.errors.main import LastAttemptError
from statement.domain.entities.account import (
    CustomerAccount,
    CustomerAccountLedger,
    CustomerAccountStatus,
    LedgerOperationType,
)
from statement.domain.entities.customer import Customer
from tests.conftest import RunEntrypoint
from tests.utils.db import DbTestUtil

CREATE_PAYMENT_ENTRYPOINT = CreatePayment.route()


async def add_account(
    db_session: AsyncSession,
    status: CustomerAccountStatus = CustomerAccountStatus.ACTIVE,
) -> CustomerAccount:
    now = datetime.now(UTC)
    customer = Customer(
        id=uuid7(),
        email=f"{uuid7()}@mail.com",
        name="customer",
        created_at=now,
        updated_at=now,
    )
    account = CustomerAccount(
        id=uuid7(),
        customer_id=customer.id,
        currency="EUR",
        name="main",
        status=status,
        created_at=now,
        updated_at=now,
        updated_by=uuid7(),
    )
    db_session.add_all([customer, account])
    # genesis ledger row
    db_session.add(CustomerAccountLedger.create(account.id, created_by=None))
    await db_session.flush()

    return account


def payment(
    account_id: UUID,
    amount: str,
    operation_type: LedgerOperationType = LedgerOperationType.DEPOSIT,
    id: UUID | None = None,
) -> bytes:
    return CreatePayment(
        id=id or uuid7(),
        account_id=account_id,
        type=operation_type,
        signed_amount=Decimal(amount),
        occurred_at=datetime.now(UTC),
    ).to_payload_bytes()


async def ledger_rows(
    db_session: AsyncSession,
    account_id: UUID,
) -> list[CustomerAccountLedger]:
    stmt = (
        sa.select(CustomerAccountLedger)
        .where(CustomerAccountLedger.account_id == account_id)
        .order_by(CustomerAccountLedger.no)
    )
    return list((await db_session.execute(stmt)).scalars().all())


@pytest.mark.anyio
async def test_deposit_appends_a_chained_row(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)

    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "25.00"))

    rows = await ledger_rows(session, account.id)
    assert [(r.no, r.amount, r.balance) for r in rows] == [
        (1, Decimal("0.00"), Decimal("0.00")),
        (2, Decimal("25.00"), Decimal("25.00")),
    ]
    assert rows[1].operation_type == LedgerOperationType.DEPOSIT


@pytest.mark.anyio
async def test_withdrawal_stores_a_negative_amount(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)
    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "100.00"))

    await run_entrypoint(
        CREATE_PAYMENT_ENTRYPOINT,
        payment(account.id, "-30.00", LedgerOperationType.WITHDRAWAL),
    )

    rows = await ledger_rows(session, account.id)
    assert (rows[-1].no, rows[-1].amount, rows[-1].balance) == (
        3,
        Decimal("-30.00"),
        Decimal("70.00"),
    )
    assert rows[-1].operation_type == LedgerOperationType.WITHDRAWAL


@pytest.mark.anyio
async def test_movements_chain_in_order(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)

    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "50.00"))
    await run_entrypoint(
        CREATE_PAYMENT_ENTRYPOINT,
        payment(account.id, "-20.00", LedgerOperationType.WITHDRAWAL),
    )
    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "5.00"))

    rows = await ledger_rows(session, account.id)
    assert [r.no for r in rows] == [1, 2, 3, 4]
    # every row is its predecessor plus its own amount
    for previous, current in zip(rows, rows[1:], strict=False):
        assert current.balance == previous.balance + current.amount
    assert rows[-1].balance == Decimal("35.00")


@pytest.mark.anyio
async def test_redelivered_command_is_applied_once(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)
    command = payment(account.id, "25.00")

    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, command)
    with capture_logs() as logs:
        await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, command)

    assert any(
        entry["event"] == "customer_account_ledger.duplicate_operation"
        for entry in logs
    )
    rows = await ledger_rows(session, account.id)
    assert [r.no for r in rows] == [1, 2]
    assert rows[-1].balance == Decimal("25.00")


@pytest.mark.anyio
async def test_withdrawal_of_exact_balance_is_allowed(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)
    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "30.00"))

    await run_entrypoint(
        CREATE_PAYMENT_ENTRYPOINT,
        payment(account.id, "-30.00", LedgerOperationType.WITHDRAWAL),
    )

    rows = await ledger_rows(session, account.id)
    assert rows[-1].balance == Decimal("0.00")


@pytest.mark.anyio
async def test_empty_payload_is_dropped(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    await add_account(session)
    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, None)

    assert await DbTestUtil.count(session, CustomerAccountLedger.__tablename__) == 1


# rejections


@pytest.mark.anyio
async def test_insufficient_balance_asks_for_a_retry(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)
    await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "30.00"))

    with capture_logs() as logs, pytest.raises(LastAttemptError):
        await run_entrypoint(
            CREATE_PAYMENT_ENTRYPOINT,
            payment(account.id, "-50.00", LedgerOperationType.WITHDRAWAL),
        )

    assert any(
        entry["event"] == "customer_account_ledger.insufficient_balance"
        and entry["log_level"] == "warning"
        for entry in logs
    )
    rows = await ledger_rows(session, account.id)
    assert [r.no for r in rows] == [1, 2]
    assert rows[-1].balance == Decimal("30.00")


@pytest.mark.anyio
async def test_unknown_account_asks_for_a_retry(
    run_entrypoint: RunEntrypoint,
    session: AsyncSession,
) -> None:
    missing = uuid7()

    with capture_logs() as logs, pytest.raises(RetryRequested):
        await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(missing, "25.00"))

    assert any(
        entry["event"] == "customer_account_ledger.unknown_account"
        and entry["log_level"] == "warning"
        for entry in logs
    )
    assert await ledger_rows(session, missing) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    [CustomerAccountStatus.DELETED, CustomerAccountStatus.DISABLED],
)
async def test_inactive_account_takes_no_movements(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
    status: CustomerAccountStatus,
) -> None:
    account = await add_account(session, status=status)

    with capture_logs() as logs, pytest.raises(LastAttemptError):
        await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, payment(account.id, "25.00"))

    assert any(
        entry["event"] == "customer_account_ledger.account_not_active"
        and entry["details"]["status"] == status
        for entry in logs
    )
    rows = await ledger_rows(session, account.id)
    assert [r.no for r in rows] == [1]


@pytest.mark.anyio
async def test_rejection_becomes_terminal_after_max_attempts(
    session: AsyncSession,
    run_entrypoint: RunEntrypoint,
) -> None:
    account = await add_account(session)
    command = payment(account.id, "-1.00", LedgerOperationType.WITHDRAWAL)

    with pytest.raises(LastAttemptError):
        await run_entrypoint(CREATE_PAYMENT_ENTRYPOINT, command, attempts=3)
