from collections.abc import AsyncIterator

from faststream.rabbit import RabbitBroker
from pgqueuer import AsyncpgDriver, Queries
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from statement.app.repository import CustomerAccountLedgerVerificationRepository
from statement.app.subscribers.base import build_broker
from statement.db import Session
from statement.domain.repository import CustomerAccountRepository, CustomerRepository
from statement.infra.repository.account import CustomerAccountRepositoryImpl
from statement.infra.repository.customer import CustomerRepositoryImpl
from statement.infra.repository.ledger_verification import (
    CustomerAccountLedgerVerificationRepositoryImpl,
)


def get_broker() -> RabbitBroker:
    return build_broker()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with Session() as session:
        yield session


async def make_queries(connection: AsyncConnection) -> Queries:
    raw_connection = await connection.get_raw_connection()
    apg_connection = raw_connection.driver_connection
    return Queries(AsyncpgDriver(apg_connection))


def get_customer_repo(session: AsyncSession) -> CustomerRepository:
    return CustomerRepositoryImpl(session)


def get_customer_account_repo(
    session: AsyncSession,
) -> CustomerAccountRepository:
    return CustomerAccountRepositoryImpl(session)


def get_ledger_verification_repo(
    session: AsyncSession,
) -> CustomerAccountLedgerVerificationRepository:
    return CustomerAccountLedgerVerificationRepositoryImpl(session)
