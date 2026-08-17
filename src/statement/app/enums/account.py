from enum import StrEnum


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
