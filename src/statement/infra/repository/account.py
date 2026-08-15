from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from statement.domain.entities.account import CustomerAccount, CustomerAccountLedger
from statement.domain.repository import CustomerAccountRepository


class CustomerAccountRepositoryImpl(CustomerAccountRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(self, entity_id: UUID) -> CustomerAccount | None:
        stmt = select(CustomerAccount).where(CustomerAccount.id == entity_id)
        result = await self.session.execute(statement=stmt)

        return result.scalar_one_or_none()

    async def lock_by_id(self, entity_id: UUID) -> CustomerAccount | None:
        stmt = (
            select(CustomerAccount)
            .where(CustomerAccount.id == entity_id)
            .with_for_update()
        )
        result = await self.session.execute(statement=stmt)

        return result.scalar_one_or_none()

    async def find_last_ledger_entry(
        self,
        account_id: UUID,
    ) -> CustomerAccountLedger | None:
        stmt = (
            select(CustomerAccountLedger)
            .where(CustomerAccountLedger.account_id == account_id)
            .order_by(CustomerAccountLedger.no.desc())
            .limit(1)
        )
        result = await self.session.execute(statement=stmt)

        return result.scalar_one_or_none()

    async def has_ledger_operation(self, account_id: UUID, operation_id: UUID) -> bool:
        stmt = select(
            select(CustomerAccountLedger)
            .where(
                CustomerAccountLedger.account_id == account_id,
                CustomerAccountLedger.operation_id == operation_id,
            )
            .exists()
        )
        result = await self.session.execute(statement=stmt)

        return bool(result.scalar_one())
