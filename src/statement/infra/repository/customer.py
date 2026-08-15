from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statement.domain.entities.customer import Customer
from statement.domain.repository import CustomerRepository


class CustomerRepositoryImpl(CustomerRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, entity_id: UUID) -> Customer | None:
        stmt = select(Customer).where(Customer.id == entity_id)
        result = await self.session.execute(statement=stmt)

        return result.scalar_one_or_none()
