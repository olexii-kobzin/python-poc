from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from faststream import Depends
from faststream.rabbit import RabbitMessage, RabbitRouter
from pgqueuer import Queries
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import bound_contextvars

from statement import deps
from statement.app.commands.local.main import CreatePayment
from statement.app.events.distributed.inbound.main import (
    CustomerCreated,
    PaymentDeposited,
    PaymentWithdrawn,
)
from statement.app.messages_base import BaseAsyncMessage
from statement.app.subscribers import base
from statement.domain.entities.account import LedgerOperationType
from statement.domain.entities.customer import Customer, CustomerStatus
from statement.infra.request_id import propagation_headers, request_id_from


async def bind_request_id(message: RabbitMessage) -> AsyncIterator[None]:
    with bound_contextvars(request_id=request_id_from(message.headers)):
        yield


router = RabbitRouter(dependencies=[Depends(bind_request_id)])
log = structlog.get_logger(__name__)


class JobEnqueuer:
    def __init__(self, queries: Queries) -> None:
        self.queries = queries

    async def enqueue(self, event: BaseAsyncMessage) -> None:
        await self.queries.enqueue(
            entrypoint=event.route(),
            payload=event.to_payload_bytes(),
            dedupe_key=event.dedupe_key(),
            headers=propagation_headers(),
        )


async def get_enqueuer(
    session: Annotated[AsyncSession, Depends(deps.get_session)],
) -> JobEnqueuer:
    connection = await session.connection()
    return JobEnqueuer(await deps.make_queries(connection))


@router.subscriber(
    queue=base.live_queue(
        name="customer.created",
        routing_key="customer.created",
        dlx=base.Exchanges.EVENTS_DLX,
    ),
    exchange=base.events_exchange,
)
async def on_customer_created(
    event: CustomerCreated,
    session: Annotated[AsyncSession, Depends(deps.get_tx_session)],
) -> None:
    customer_repo = deps.get_customer_repo(session)
    customer = await customer_repo.find_by_id(event.id)
    if customer is not None:
        return None

    customer = Customer.create(
        entity_id=event.id,
        email=event.email,
        name=event.name,
        status=CustomerStatus(event.status),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )
    session.add(customer)


@router.subscriber(
    queue=base.live_queue(
        name="payment.deposited",
        routing_key="payment.deposited",
        dlx=base.Exchanges.EVENTS_DLX,
    ),
    exchange=base.events_exchange,
)
async def on_payment_deposited(
    event: PaymentDeposited,
    session: Annotated[AsyncSession, Depends(deps.get_tx_session)],
    enqueuer: Annotated[JobEnqueuer, Depends(get_enqueuer)],
) -> None:
    await enqueuer.enqueue(
        CreatePayment(
            id=event.id,
            account_id=event.account_id,
            type=LedgerOperationType.DEPOSIT,
            signed_amount=event.amount,
            occurred_at=event.occurred_at,
        )
    )


@router.subscriber(
    queue=base.live_queue(
        name="payment.withdrawn",
        routing_key="payment.withdrawn",
        dlx=base.Exchanges.EVENTS_DLX,
    ),
    exchange=base.events_exchange,
)
async def on_payment_withdrawn(
    event: PaymentWithdrawn,
    session: Annotated[AsyncSession, Depends(deps.get_tx_session)],
    enqueuer: Annotated[JobEnqueuer, Depends(get_enqueuer)],
) -> None:
    await enqueuer.enqueue(
        CreatePayment(
            id=event.id,
            account_id=event.account_id,
            type=LedgerOperationType.WITHDRAWAL,
            signed_amount=event.amount * -1,
            occurred_at=event.occurred_at,
        )
    )
