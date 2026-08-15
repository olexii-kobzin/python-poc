"""Entity package.

Importing this package registers every mapped class with the declarative
registry. Relationships reference their targets by name (e.g. ``"Customer"``),
and SQLAlchemy can only resolve those names for classes that have actually been
imported -- so every entity module must be imported here.
"""

from statement.domain.entities.account import (
    CustomerAccountStatus,
    CustomerAccount,
    CustomerAccountHistory,
    CustomerAccountLedger,
    LedgerOperationType,
)
from statement.domain.entities.customer import CustomerStatus, Customer
from statement.domain.entities.base import Base

__all__ = [
    "Base",
    "Customer",
    "CustomerAccount",
    "CustomerAccountHistory",
    "CustomerAccountLedger",
    "CustomerAccountStatus",
    "CustomerStatus",
]
