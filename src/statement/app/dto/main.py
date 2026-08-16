from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from statement.infra.models import LedgerDiscrepancyKind


@dataclass(frozen=True, slots=True)
class AccountVerification:
    """One account's verdict for one batch."""

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
