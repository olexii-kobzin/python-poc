"""Entity package.

Importing this package registers every mapped class with the declarative
registry. Relationships reference their targets by name (e.g. ``"Customer"``),
and SQLAlchemy can only resolve those names for classes that have actually been
imported -- so every entity module must be imported here.
"""

from statement.domain.entities.account import (
    CustomerAccount,
    CustomerAccountHistory,
    CustomerAccountLedger,
    CustomerAccountStatus,
    LedgerOperationType,
)
from statement.domain.entities.base import Base
from statement.domain.entities.customer import Customer, CustomerStatus

__all__ = [
    "Base",
    "Customer",
    "CustomerAccount",
    "CustomerAccountHistory",
    "CustomerAccountLedger",
    "CustomerAccountStatus",
    "CustomerStatus",
    "LedgerOperationType",
]
