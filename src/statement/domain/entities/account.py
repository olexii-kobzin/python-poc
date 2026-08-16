from datetime import datetime, UTC
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Self
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint, PrimaryKeyConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship, reconstructor

from statement.domain.entities.base import Base
from statement.persistence.versioned_history import VersionedHistory

if TYPE_CHECKING:
    from statement.domain.entities.customer import Customer


class CustomerAccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class LedgerOperationType(StrEnum):
    # the zero-amount row every account creates with, so the chain always has a
    # predecessor and `no` starts dense at 1
    CREATE = "create"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class CustomerAccount(Base, VersionedHistory):
    __tablename__ = "customer_account"

    use_mapper_versioning = True

    id: Mapped[UUID] = mapped_column(sa.Uuid(), primary_key=True, name="id")
    customer_id: Mapped[UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("customer.id"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(sa.Text(), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    status: Mapped[CustomerAccountStatus] = mapped_column(
        sa.Enum(
            CustomerAccountStatus,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=CustomerAccountStatus.ACTIVE,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    updated_by: Mapped[UUID] = mapped_column(sa.Uuid())

    customer: Mapped[Customer] = relationship(back_populates="accounts")

    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "currency",
            name="uq_customer_account_customer_id_currency"
        ),
    )

    @classmethod
    def create(
        cls,
        entity_id: UUID,
        customer_id: UUID,
        currency: str,
        name: str | None,
        updated_by: UUID,
    ) -> Self:
        now = datetime.now(UTC)

        return cls(
            id=entity_id,
            customer_id=customer_id,
            currency=currency,
            name=name,
            status=CustomerAccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            updated_by=updated_by,
        )


CustomerAccountHistory = CustomerAccount.__history_mapper__.class_


class CustomerAccountLedger(Base):
    __tablename__ = "customer_account_ledger"

    account_id: Mapped[UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("customer_account.id"),
    )
    no: Mapped[int] = mapped_column(
        sa.BigInteger()
    )
    amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(
            precision=16,
            scale=2,
            decimal_return_scale=2,
            asdecimal=True,
        ),
        nullable=False,
    )
    balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(
            precision=16,
            scale=2,
            decimal_return_scale=2,
            asdecimal=True,
        ),
        nullable=False,
    )
    operation_type: Mapped[LedgerOperationType] = mapped_column(
        sa.Enum(
            LedgerOperationType,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    operation_id: Mapped[UUID] = mapped_column(sa.Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
    )
    # NULL = written by the system (e.g. payment consumers), not a human actor
    created_by: Mapped[UUID | None] = mapped_column(sa.Uuid(), nullable=True)

    customer_account: Mapped[CustomerAccount] = relationship()

    @classmethod
    def create(cls, entity_id: UUID, created_by: UUID | None) -> Self:
        return cls(
            account_id=entity_id,
            no=1,
            amount=Decimal(0),
            balance=Decimal(0),
            operation_type=LedgerOperationType.CREATE,
            operation_id=entity_id,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )

    @classmethod
    def follow(
        cls,
        previous: Self,
        amount: Decimal,
        operation_type: LedgerOperationType,
        operation_id: UUID,
        created_by: UUID | None,
    ) -> Self:
        return cls(
            account_id=previous.account_id,
            no=previous.no + 1,
            amount=amount,
            balance=previous.balance + amount,
            operation_type=operation_type,
            operation_id=operation_id,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )

    __table_args__ = (
        PrimaryKeyConstraint("account_id", "no"),
        UniqueConstraint(
            "account_id",
            "operation_id",
            name="uq_customer_account_ledger_account_id_operation_id",
        ),
        Index(
            "ix_customer_account_ledger_account_id_created_at",
            "account_id",
            "created_at",
        ),
    )
