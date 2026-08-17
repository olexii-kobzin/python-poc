from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from statement.app.enums.account import LedgerDiscrepancyKind


@dataclass(frozen=True, slots=True)
class CustomerAccountVerification:
    account_id: UUID
    anchor_no: int
    anchor_balance: Decimal
    batch_rows: int
    batch_limit: int
    batch_last_no: int
    batch_last_balance: Decimal
    break_no: int | None
    break_kind: str | None
    break_amount: Decimal | None
    break_balance: Decimal | None
    break_prev_no: int | None
    break_prev_balance: Decimal | None

    @property
    def last_good_no(self) -> int:
        if self.break_prev_no is None:
            return self.batch_last_no
        return self.break_prev_no

    @property
    def last_good_balance(self) -> Decimal:
        if self.break_prev_balance is None:
            return self.batch_last_balance
        return self.break_prev_balance

    @property
    def should_checkpoint(self) -> bool:
        return self.last_good_no > self.anchor_no

    @property
    def expected_balance(self) -> Decimal | None:
        if self.break_kind is None or self.break_kind == LedgerDiscrepancyKind.GAP:
            return None
        if self.break_kind == LedgerDiscrepancyKind.ANCHOR_BALANCE:
            return self.anchor_balance
        return (self.break_prev_balance or Decimal(0)) + (
            self.break_amount or Decimal(0)
        )


@dataclass(frozen=True, slots=True)
class CustomerAccountLedgerVerified:
    account_id: UUID
    through_no: int
    balance: Decimal
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerAccountLedgerDiscrepancy:
    discrepancy_id: int
    account_id: UUID
    no: int
    kind: str
    prev_no: int
    expected_balance: Decimal | None
    actual_balance: Decimal
    detected_at: datetime
    resolved_at: datetime | None
    resolved_by: UUID | None
