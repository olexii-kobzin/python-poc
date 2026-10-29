import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid7

import pytest
from faststream.rabbit import RabbitBroker
from pgqueuer import RetryRequested

from statement.app.errors.main import LastAttemptError
from statement.app.events.distributed.outgoing.main import (
    CustomerAccountCreatedOutgoing,
)
from statement.app.events.local.main import CustomerAccountCreated
from statement.app.subscribers.base import events_exchange
from tests.conftest import RunEntrypoint

ENTRYPOINT = CustomerAccountCreated.route()


def local_event() -> CustomerAccountCreated:
    now = datetime.now(UTC)
    return CustomerAccountCreated(
        id=uuid7(),
        customer_id=uuid7(),
        currency="EUR",
        name="main",
        status="active",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def publish(broker: RabbitBroker, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Spy on the very broker object the entrypoint reads from its resources."""
    mock = AsyncMock()
    monkeypatch.setattr(broker, "publish", mock)

    return mock


def test_routes_of_local_and_outgoing_event_match() -> None:
    """The local job route is also the AMQP routing key; a drift would orphan it."""
    assert CustomerAccountCreatedOutgoing.route() == ENTRYPOINT


@pytest.mark.anyio
async def test_publishes_the_event_to_the_events_exchange(
    run_entrypoint: RunEntrypoint,
    publish: AsyncMock,
) -> None:
    event = local_event()

    await run_entrypoint(ENTRYPOINT, event.to_payload_bytes())

    publish.assert_awaited_once()
    call = publish.await_args
    assert call is not None
    assert call.kwargs["routing_key"] == "customer-account.created"
    assert call.kwargs["exchange"] is events_exchange
    assert call.kwargs["content_type"] == "application/json"

    body = json.loads(call.args[0])
    assert body["id"] == str(event.id)
    assert body["customer_id"] == str(event.customer_id)
    assert body["currency"] == "EUR"
    assert body["name"] == "main"
    assert body["status"] == "active"


@pytest.mark.anyio
async def test_undecodable_payload_publishes_nothing(
    run_entrypoint: RunEntrypoint,
    publish: AsyncMock,
) -> None:
    with pytest.raises(LastAttemptError):
        await run_entrypoint(ENTRYPOINT, b'{"id": "not-a-uuid"}')

    publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_failure_asks_for_a_retry(
    run_entrypoint: RunEntrypoint,
    publish: AsyncMock,
) -> None:
    publish.side_effect = ConnectionError("broker down")

    with pytest.raises(RetryRequested):
        await run_entrypoint(ENTRYPOINT, local_event().to_payload_bytes())
