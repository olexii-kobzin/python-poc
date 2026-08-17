from abc import abstractmethod
from typing import Protocol, runtime_checkable
from uuid import UUID

from statement.domain.entities.account import CustomerAccount, CustomerAccountLedger
from statement.domain.entities.customer import Customer


# runtime_checkable: fast_depends builds an isinstance validator for handler
# params annotated with this Protocol; a plain Protocol is not a valid
# isinstance target and crashes subscriber startup
@runtime_checkable
class CustomerRepository(Protocol):
    @abstractmethod
    async def find_by_id(self, entity_id: UUID) -> Customer | None:
        pass


class CustomerAccountRepository(Protocol):
    @abstractmethod
    async def find_by_id(self, entity_id: UUID) -> CustomerAccount | None:
        pass

    @abstractmethod
    async def lock_by_id(self, entity_id: UUID) -> CustomerAccount | None:
        """Take the row lock that serialises ledger writes for this account.

        Held to commit, it is what makes ``no`` become visible in the order it
        was handed out -- the assumption the verifier's checkpointing rests on.
        """

    @abstractmethod
    async def find_last_ledger_entry(
        self,
        account_id: UUID,
    ) -> CustomerAccountLedger | None:
        pass

    @abstractmethod
    async def has_ledger_operation(self, account_id: UUID, operation_id: UUID) -> bool:
        pass
