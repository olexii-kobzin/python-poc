from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Identity, Index, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from statement.domain.entities import Base


class LedgerDiscrepancyKind(StrEnum):
    # an already-verified row's balance changed since it was checkpointed
    ANCHOR_BALANCE = "anchor_balance"
    # no <> prev_no + 1, but the running total still adds up: the numbering has
    # a hole and no amounts went missing with it
    GAP = "gap"
    # balance <> prev_balance + amount -- the running total broke
    BALANCE = "balance"
    # both at once: rows are missing *and* they took their amounts with them.
    # expected_balance - actual_balance is what the missing rows summed to
    GAP_BALANCE = "gap_balance"


class CustomerAccountLedgerVerified(Base):
    __tablename__ = "customer_account_ledger_verified"

    account_id: Mapped[UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("customer_account.id"),
    )
    through_no: Mapped[int] = mapped_column(
        sa.BigInteger()
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
    verified_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
    )

    __table_args__ = (
        PrimaryKeyConstraint("account_id", "through_no"),
        Index(
            "ix_customer_account_ledger_verified_account_id_verified_at",
            "account_id",
            "verified_at",
        ),
    )


class CustomerAccountLedgerDiscrepancy(Base):
    """Incident log for ledger chain breaks.

    Doubles as the quarantine flag: the verifier skips any account holding an
    unresolved row, so one bad account cannot monopolise every batch. The
    partial unique index below is what makes "at most one open incident per
    account" a schema guarantee rather than a convention.
    """

    __tablename__ = "customer_account_ledger_discrepancy"

    discrepancy_id: Mapped[int] = mapped_column(
        sa.BigInteger(),
        Identity(),
        primary_key=True,
    )
    account_id: Mapped[UUID] = mapped_column(
        sa.Uuid(),
        sa.ForeignKey("customer_account.id"),
        nullable=False,
    )
    no: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    # values_callable: persist the lowercase values ("gap"), not the member
    # names ("GAP") that sa.Enum stores by default
    kind: Mapped[LedgerDiscrepancyKind] = mapped_column(
        sa.Enum(
            LedgerDiscrepancyKind,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        index=True,
    )
    # last row that still held: for a gap this is not no - 1
    prev_no: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    # NULL only for a plain gap: there the running total still adds up, so
    # there is no balance expectation to record. Set for gap_balance
    expected_balance: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(
            precision=16,
            scale=2,
            decimal_return_scale=2,
            asdecimal=True,
        ),
        nullable=True,
    )
    actual_balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(
            precision=16,
            scale=2,
            decimal_return_scale=2,
            asdecimal=True,
        ),
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    resolved_by: Mapped[UUID | None] = mapped_column(sa.Uuid(), nullable=True)

    __table_args__ = (
        Index(
            "uq_customer_account_ledger_discrepancy_open",
            "account_id",
            unique=True,
            postgresql_where=sa.text("resolved_at IS NULL"),
        ),
    )