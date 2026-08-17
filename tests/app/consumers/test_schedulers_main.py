from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from statement.app.enums.account import LedgerDiscrepancyKind
from statement.conf import settings
from statement.domain.entities.account import CustomerAccount, CustomerAccountLedger
from statement.domain.entities.customer import Customer
from statement.infra.models.account import (
    CustomerAccountLedgerDiscrepancy,
    CustomerAccountLedgerVerified,
)
from tests.utils.db import DbTestUtil

SCHEDULE = "customer_account_ledger_verify"

RunSchedule = Callable[[str], Awaitable[None]]


async def add_account(session: AsyncSession) -> CustomerAccount:
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
        created_at=now,
        updated_at=now,
        updated_by=uuid7(),
    )
    session.add_all([customer, account])
    await session.flush()

    return account


async def add_ledger_rows(
    session: AsyncSession,
    account: CustomerAccount,
    amounts: list[Decimal],
    *,
    start_no: int = 1,
    start_balance: Decimal = Decimal(0),
) -> None:
    balance = start_balance
    for offset, amount in enumerate(amounts):
        balance += amount
        session.add(
            CustomerAccountLedger(
                account_id=account.id,
                no=start_no + offset,
                amount=amount,
                balance=balance,
                operation_type="deposit",
                operation_id=uuid7(),
                created_at=datetime.now(UTC),
                created_by=None,
            )
        )
    await session.flush()


async def add_checkpoint(
    session: AsyncSession,
    account_id: UUID,
    through_no: int,
    balance: Decimal,
    verified_at: datetime | None = None,
) -> None:
    session.add(
        CustomerAccountLedgerVerified(
            account_id=account_id,
            through_no=through_no,
            balance=balance,
            verified_at=verified_at or datetime.now(UTC),
        )
    )
    await session.flush()


async def latest_checkpoint(
    session: AsyncSession,
    account_id: UUID,
) -> CustomerAccountLedgerVerified | None:
    import sqlalchemy as sa

    stmt = (
        sa.select(CustomerAccountLedgerVerified)
        .where(CustomerAccountLedgerVerified.account_id == account_id)
        .order_by(CustomerAccountLedgerVerified.through_no.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@pytest.fixture(autouse=True)
def small_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the window small enough that a handful of rows can fill it."""
    monkeypatch.setattr(settings, "ledger_verify_rows_per_account", 3)
    monkeypatch.setattr(settings, "ledger_verify_accounts_per_run", 10)
    monkeypatch.setattr(settings, "ledger_verify_max_checkpoint_age_seconds", 3600)


@pytest.mark.anyio
async def test_never_verified_account_is_checkpointed(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)

    await run_schedule(SCHEDULE)

    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 3
    assert checkpoint.balance == Decimal("30.00")


@pytest.mark.anyio
async def test_full_window_is_checkpointed_behind_a_fresh_anchor(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)
    await add_checkpoint(session, account.id, through_no=3, balance=Decimal("30.00"))

    # anchor row + 3 new rows exactly fills rows_per_account + 1
    await add_ledger_rows(
        session,
        account,
        [Decimal("5.00")] * 3,
        start_no=4,
        start_balance=Decimal("30.00"),
    )

    await run_schedule(SCHEDULE)

    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 6
    assert checkpoint.balance == Decimal("45.00")


@pytest.mark.anyio
async def test_partial_window_is_not_checkpointed(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)
    await add_checkpoint(session, account.id, through_no=3, balance=Decimal("30.00"))

    # one new row: the window reads anchor + 1, well short of its limit
    await add_ledger_rows(
        session,
        account,
        [Decimal("5.00")],
        start_no=4,
        start_balance=Decimal("30.00"),
    )

    await run_schedule(SCHEDULE)

    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 3
    assert (
        await DbTestUtil.count(
            session,
            CustomerAccountLedgerVerified.__tablename__,
            {"account_id": account.id},
        )
        == 1
    )


@pytest.mark.anyio
async def test_partial_window_is_checkpointed_once_anchor_goes_stale(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)
    await add_checkpoint(
        session,
        account.id,
        through_no=3,
        balance=Decimal("30.00"),
        verified_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await add_ledger_rows(
        session,
        account,
        [Decimal("5.00")],
        start_no=4,
        start_balance=Decimal("30.00"),
    )

    await run_schedule(SCHEDULE)

    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 4
    assert checkpoint.balance == Decimal("35.00")


@pytest.mark.anyio
async def test_balance_diescrepancy(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 2)
    # balance should be 30.00 -- the chain breaks here
    session.add(
        CustomerAccountLedger(
            account_id=account.id,
            no=3,
            amount=Decimal("10.00"),
            balance=Decimal("999.00"),
            operation_type="deposit",
            operation_id=uuid7(),
            created_at=datetime.now(UTC),
            created_by=None,
        )
    )
    await session.flush()

    with capture_logs() as logs:
        await run_schedule(SCHEDULE)

    warnings = [
        entry
        for entry in logs
        if entry["event"] == "customer_account_ledger.discrepancy"
    ]
    assert warnings[0] == {
        "event": "customer_account_ledger.discrepancy",
        "log_level": "warning",
        "details": {
            "account_id": str(account.id),
            "kind": LedgerDiscrepancyKind.BALANCE,
            "no": 3,
            "prev_no": 2,
            "verified_through_no": 0,
            "expected_balance": "30.00",
            "actual_balance": "999.00",
        },
    }

    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {
            "account_id": account.id,
            "no": 3,
            "resolved_at__isnull": True,
            "prev_no": 2,
            "expected_balance": Decimal("30.00"),
            "actual_balance": Decimal("999.00"),
        },
    )

    # the good prefix is banked, the broken row is not
    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 2
    assert checkpoint.balance == Decimal("20.00")


@pytest.mark.anyio
async def test_gap_discrepancy(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 2)
    # no 3 is missing; balance still chains off row 2, so only numbering broke
    await add_ledger_rows(
        session,
        account,
        [Decimal("10.00")],
        start_no=4,
        start_balance=Decimal("20.00"),
    )

    with capture_logs() as logs:
        await run_schedule(SCHEDULE)

    warnings = [
        entry
        for entry in logs
        if entry["event"] == "customer_account_ledger.discrepancy"
    ]
    assert warnings[0] == {
        "event": "customer_account_ledger.discrepancy",
        "log_level": "warning",
        "details": {
            "account_id": str(account.id),
            "kind": LedgerDiscrepancyKind.GAP,
            "no": 4,
            "prev_no": 2,
            "verified_through_no": 0,
            "expected_balance": "None",
            "actual_balance": "30.00",
        },
    }

    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {
            "account_id": account.id,
            "no": 4,
            "kind": LedgerDiscrepancyKind.GAP,
            "prev_no": 2,
            "expected_balance": None,
            "actual_balance": Decimal("30.00"),
        },
    )

    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 2
    assert checkpoint.balance == Decimal("20.00")


@pytest.mark.anyio
async def test_gap_balance_discrepancy(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 2)
    # nos 3-4 are missing and took their +20.00 with them: row 5 chains off a
    # balance of 40.00, but the last surviving row holds 20.00
    await add_ledger_rows(
        session,
        account,
        [Decimal("10.00")],
        start_no=5,
        start_balance=Decimal("40.00"),
    )

    with capture_logs() as logs:
        await run_schedule(SCHEDULE)

    warnings = [
        entry
        for entry in logs
        if entry["event"] == "customer_account_ledger.discrepancy"
    ]
    assert warnings[0] == {
        "event": "customer_account_ledger.discrepancy",
        "log_level": "warning",
        "details": {
            "account_id": str(account.id),
            "kind": LedgerDiscrepancyKind.GAP_BALANCE,
            "no": 5,
            "prev_no": 2,
            "verified_through_no": 0,
            "expected_balance": "30.00",
            "actual_balance": "50.00",
        },
    }

    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {
            "account_id": account.id,
            "no": 5,
            "kind": LedgerDiscrepancyKind.GAP_BALANCE,
            "prev_no": 2,
            "expected_balance": Decimal("30.00"),
            "actual_balance": Decimal("50.00"),
            "resolved_at__isnull": True,
        },
    )

    checkpoint = await latest_checkpoint(session, account.id)
    assert checkpoint is not None
    assert checkpoint.through_no == 2
    assert checkpoint.balance == Decimal("20.00")


@pytest.mark.anyio
async def test_open_discrepancy_quarantines_the_account(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)
    session.add(
        CustomerAccountLedgerDiscrepancy(
            account_id=account.id,
            no=1,
            kind=LedgerDiscrepancyKind.BALANCE,
            prev_no=0,
            expected_balance=Decimal("0.00"),
            actual_balance=Decimal("10.00"),
            detected_at=datetime.now(UTC),
            resolved_at=None,
        )
    )
    await session.flush()

    await run_schedule(SCHEDULE)

    assert await latest_checkpoint(session, account.id) is None
    assert (
        await DbTestUtil.count(
            session,
            CustomerAccountLedgerDiscrepancy.__tablename__,
            {"account_id": account.id},
        )
        == 1
    )


@pytest.mark.anyio
async def test_anchor_balance_discrepancy(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)
    # checkpoint claims row 3 held 30.00; the ledger row says otherwise
    await add_checkpoint(
        session,
        account.id,
        through_no=3,
        balance=Decimal("99.00"),
        verified_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await add_ledger_rows(
        session,
        account,
        [Decimal("5.00")],
        start_no=4,
        start_balance=Decimal("30.00"),
    )

    with capture_logs() as logs:
        await run_schedule(SCHEDULE)

    warnings = [
        entry
        for entry in logs
        if entry["event"] == "customer_account_ledger.discrepancy"
    ]
    assert warnings[0] == {
        "event": "customer_account_ledger.discrepancy",
        "log_level": "warning",
        "details": {
            "account_id": str(account.id),
            "kind": LedgerDiscrepancyKind.ANCHOR_BALANCE,
            "no": 3,
            "prev_no": 3,
            "verified_through_no": 3,
            "expected_balance": "99.00",
            "actual_balance": "30.00",
        },
    }

    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {
            "account_id": account.id,
            "no": 3,
            "kind": LedgerDiscrepancyKind.ANCHOR_BALANCE,
            "prev_no": 3,
            "expected_balance": Decimal("99.00"),
            "actual_balance": Decimal("30.00"),
        },
    )


@pytest.mark.anyio
async def test_clean_account_with_no_new_rows_is_skipped(
    session: AsyncSession,
    run_schedule: RunSchedule,
) -> None:
    account = await add_account(session)
    await add_ledger_rows(session, account, [Decimal("10.00")] * 3)
    await add_checkpoint(session, account.id, through_no=3, balance=Decimal("30.00"))

    await run_schedule(SCHEDULE)

    assert (
        await DbTestUtil.count(
            session,
            CustomerAccountLedgerVerified.__tablename__,
            {"account_id": account.id},
        )
        == 1
    )
