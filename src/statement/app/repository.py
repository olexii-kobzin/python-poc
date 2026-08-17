from abc import abstractmethod
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from statement.app.dto.main import (
    CustomerAccountLedgerDiscrepancy,
    CustomerAccountLedgerVerified,
    CustomerAccountVerification,
)
from statement.app.schemas.account import (
    CustomerAccountDisplay,
    CustomerAccountListQuery,
    CustomerAccountListQueryCursor,
)


class CustomerAccountReadRepository(Protocol):
    @abstractmethod
    async def list_all(
        self,
        query: CustomerAccountListQuery,
    ) -> tuple[list[CustomerAccountDisplay], CustomerAccountListQueryCursor | None]:
        pass


class CustomerAccountLedgerVerificationRepository(Protocol):
    @abstractmethod
    async def next_batch(
        self,
        accounts_per_run: int,
        rows_per_account: int,
        max_checkpoint_age_seconds: int,
    ) -> list[CustomerAccountVerification]:
        pass

    @abstractmethod
    async def add_checkpoint(
        self,
        account_id: UUID,
        through_no: int,
        balance: Decimal,
    ) -> None:
        pass

    @abstractmethod
    async def record_verified(self, verification: CustomerAccountVerification) -> None:
        pass

    @abstractmethod
    async def record_discrepancy(
        self, verification: CustomerAccountVerification
    ) -> None:
        pass

    @abstractmethod
    async def resolve_discrepancy(
        self,
        discrepancy_id: int,
        account_id: UUID,
        resolved_by: UUID,
    ) -> None:
        pass

    @abstractmethod
    async def find_open_discrepancy(
        self,
        account_id: UUID,
    ) -> CustomerAccountLedgerDiscrepancy | None:
        pass

    @abstractmethod
    async def find_latest_checkpoint(
        self,
        account_id: UUID,
    ) -> CustomerAccountLedgerVerified | None:
        pass

    @abstractmethod
    async def find_ledger_balance(
        self,
        account_id: UUID,
        no: int,
    ) -> Decimal | None:
        pass
