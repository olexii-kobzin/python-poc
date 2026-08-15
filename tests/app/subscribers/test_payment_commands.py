from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app.commands.local.main import CreatePayment
from statement.app.events.distributed.inbound.main import (
    PaymentDeposited,
    PaymentWithdrawn,
)
from statement.app.subscribers.main import (
    JobEnqueuer,
    on_payment_deposited,
    on_payment_withdrawn,
)
from statement.domain.entities.account import LedgerOperationType


@pytest.fixture
def queries() -> AsyncMock:
    return AsyncMock()


def enqueued_command(queries: AsyncMock) -> CreatePayment:
    queries.enqueue.assert_awaited_once()
    payload = queries.enqueue.await_args.kwargs["payload"]
    command = CreatePayment.from_payload_bytes(payload)
    assert command is not None
    return command


def deposit(
    account_id: UUID,
    amount: str,
    entity_id: UUID | None = None,
) -> PaymentDeposited:
    return PaymentDeposited(
        id=entity_id or uuid7(),
        account_id=account_id,
        amount=Decimal(amount),
        occurred_at=datetime.now(UTC),
    )


def withdrawal(
    account_id: UUID,
    amount: str,
    entity_id: UUID | None = None,
) -> PaymentWithdrawn:
    return PaymentWithdrawn(
        id=entity_id or uuid7(),
        account_id=account_id,
        amount=Decimal(amount),
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_deposit_is_enqueued_as_a_positive_command(
    session: AsyncSession,
    queries: AsyncMock,
) -> None:
    event = deposit(uuid7(), "25.00")

    await on_payment_deposited(event, session, JobEnqueuer(queries))

    assert queries.enqueue.await_args.kwargs["entrypoint"] == CreatePayment.route()

    command = enqueued_command(queries)

    assert command.type == LedgerOperationType.DEPOSIT
    assert command.signed_amount == Decimal("25.00")
    assert (command.id, command.account_id, command.occurred_at) == (
        event.id,
        event.account_id,
        event.occurred_at,
    )


@pytest.mark.anyio
async def test_withdrawal_is_enqueued_with_the_sign_flipped(
    session: AsyncSession,
    queries: AsyncMock,
) -> None:
    event = withdrawal(uuid7(), "30.00")

    await on_payment_withdrawn(event, session, JobEnqueuer(queries))

    assert queries.enqueue.await_args.kwargs["entrypoint"] == CreatePayment.route()

    command = enqueued_command(queries)
    assert command.type == LedgerOperationType.WITHDRAWAL
    assert command.signed_amount == Decimal("-30.00")


@pytest.mark.anyio
async def test_redelivered_event_reuses_the_dedupe_key(
    session: AsyncSession,
    queries: AsyncMock,
) -> None:
    event = deposit(uuid7(), "25.00")

    await on_payment_deposited(event, session, JobEnqueuer(queries))
    first = queries.enqueue.await_args.kwargs["dedupe_key"]

    queries.enqueue.reset_mock()
    await on_payment_deposited(event, session, JobEnqueuer(queries))
    second = queries.enqueue.await_args.kwargs["dedupe_key"]

    assert first == second


@pytest.mark.anyio
async def test_deposit_and_withdrawal_of_one_entity_id_do_not_collide(
    session: AsyncSession,
    queries: AsyncMock,
) -> None:
    shared = uuid7()

    await on_payment_deposited(
        deposit(uuid7(), "25.00", entity_id=shared),
        session,
        JobEnqueuer(queries),
    )
    deposit_key = queries.enqueue.await_args.kwargs["dedupe_key"]

    queries.enqueue.reset_mock()
    await on_payment_withdrawn(
        withdrawal(uuid7(), "25.00", entity_id=shared),
        session,
        JobEnqueuer(queries),
    )
    withdrawal_key = queries.enqueue.await_args.kwargs["dedupe_key"]

    assert deposit_key == withdrawal_key, (
        "documented behaviour: operation ids are assumed globally unique across "
        "deposits and withdrawals -- if that assumption ever breaks, the dedupe "
        "key has to carry the operation type"
    )


@pytest.mark.anyio
async def test_non_positive_amount_is_rejected_by_the_schema() -> None:
    with pytest.raises(ValidationError):
        deposit(uuid7(), "0.00")
    with pytest.raises(ValidationError):
        withdrawal(uuid7(), "-5.00")
