from abc import ABC, abstractmethod
from decimal import Decimal

from uuid import UUID

from statement.app.dto.main import AccountVerification
from statement.app.schemas.account import CustomerAccountDisplay, CustomerAccountListQuery, \
    CustomerAccountListQueryCursor
from statement.infra.models import CustomerAccountLedgerVerified, CustomerAccountLedgerDiscrepancy


class CustomerAccountReadRepository(ABC):

    @abstractmethod
    async def list_all(
        self,
        query: CustomerAccountListQuery,
    ) -> tuple[list[CustomerAccountDisplay], CustomerAccountListQueryCursor | None]:
        pass

class CustomerAccountLedgerVerificationRepository(ABC):
    @abstractmethod
    async def next_batch(
        self,
        accounts_per_run: int,
        rows_per_account: int,
        max_checkpoint_age_seconds: int,
    ) -> list[AccountVerification]:
        pass

    @abstractmethod
    def add_checkpoint(
        self,
        account_id: UUID,
        through_no: int,
        balance: Decimal,
    ) -> None:
        pass

    @abstractmethod
    def record_verified(self, verification: AccountVerification) -> None:
        pass

    @abstractmethod
    def record_discrepancy(self, verification: AccountVerification) -> None:
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
