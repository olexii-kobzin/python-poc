"""Ledger chain verification.

The ledger stores a running ``balance`` per row instead of a periodic snapshot,
so the invariant that has to hold for every account is::

    balance(no) = balance(no - 1) + amount(no) -- the chain
    no = no (previous row) + 1 -- dense, gapless

``customer_account_ledger_verified`` records how far that has been checked, so
each run only walks the tail. What makes the checkpoint trustworthy is the
``FOR UPDATE`` lock the writer holds across assign-``no`` -> insert -> commit:
it forces rows to become visible in ``no`` order, so nothing can ever appear
*behind* a checkpoint.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app.dto.main import (
    CustomerAccountLedgerDiscrepancy as CustomerAccountLedgerDiscrepancyDto,
)
from statement.app.dto.main import (
    CustomerAccountLedgerVerified as CustomerAccountLedgerVerifiedDto,
)
from statement.app.dto.main import (
    CustomerAccountVerification,
)
from statement.app.enums.account import LedgerDiscrepancyKind
from statement.app.repository import CustomerAccountLedgerVerificationRepository
from statement.domain.entities.account import CustomerAccountLedger
from statement.infra.models.account import (
    CustomerAccountLedgerDiscrepancy,
    CustomerAccountLedgerVerified,
)

_BATCH_SQL = sa.text(
    """
WITH targets AS (
    SELECT a.id AS account_id,
           COALESCE(v.through_no, 0) AS anchor_no,
           COALESCE(v.balance, 0) AS anchor_balance
    FROM customer_account a
    LEFT JOIN LATERAL (
        SELECT v.through_no, v.balance, v.verified_at
        FROM customer_account_ledger_verified v
        WHERE v.account_id = a.id
        ORDER BY v.through_no DESC
        LIMIT 1
    ) v ON true
    WHERE
    (
        v.verified_at IS NULL
        OR v.verified_at < now() - make_interval(secs => :max_checkpoint_age)
        OR EXISTS (SELECT 1
                   FROM customer_account_ledger l
                   WHERE l.account_id = a.id
                    AND l.no - COALESCE(v.through_no, 0) >= :rows_per_account
                   ORDER BY l.no DESC
                   LIMIT 1)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM customer_account_ledger_discrepancy d
        WHERE d.account_id = a.id AND d.resolved_at IS NULL
    )
    AND EXISTS (
        SELECT 1
        FROM customer_account_ledger l
        WHERE l.account_id = a.id AND l.no > COALESCE(v.through_no, 0)
    )
    ORDER BY v.verified_at ASC NULLS FIRST
    LIMIT :accounts_per_run
),
windowed AS (
    SELECT t.account_id, t.anchor_no, t.anchor_balance,
           l.no, l.amount, l.balance,
           COUNT(*) OVER (PARTITION BY t.account_id) AS batch_rows,
           LAG(l.no) OVER (PARTITION BY t.account_id ORDER BY l.no) AS prev_no,
           LAG(l.balance) OVER (PARTITION BY t.account_id ORDER BY l.no) AS prev_balance
    FROM targets t
    JOIN LATERAL (
        SELECT l.no, l.amount, l.balance
        FROM customer_account_ledger l
        WHERE l.account_id = t.account_id AND l.no >= t.anchor_no
        ORDER BY l.no
        LIMIT :window_rows
    ) l ON true
),
chained AS (
    SELECT w.*,
           COALESCE(w.prev_no, w.anchor_no) AS chain_prev_no,
           COALESCE(w.prev_balance, w.anchor_balance) AS chain_prev_balance
    FROM windowed w
),
flagged AS (
    SELECT c.*,
           CASE
               WHEN c.no = c.anchor_no AND c.balance <> c.anchor_balance
                   THEN 'anchor_balance'
               WHEN c.no > c.anchor_no
                    AND c.no <> c.chain_prev_no + 1
                    AND c.balance <> c.chain_prev_balance + c.amount
                   THEN 'gap_balance'
               WHEN c.no > c.anchor_no AND c.no <> c.chain_prev_no + 1
                   THEN 'gap'
               WHEN c.no > c.anchor_no
                    AND c.balance <> c.chain_prev_balance + c.amount
                   THEN 'balance'
           END AS kind
    FROM chained c
),
first_break AS (
    SELECT DISTINCT ON (f.account_id)
           f.account_id, f.no, f.kind, f.amount, f.balance,
           f.chain_prev_no, f.chain_prev_balance
    FROM flagged f
    WHERE f.kind IS NOT NULL
    ORDER BY f.account_id, f.no
),
batch_tail AS (
    SELECT DISTINCT ON (f.account_id) f.account_id, f.no, f.balance, f.batch_rows
    FROM flagged f
    ORDER BY f.account_id, f.no DESC
)
SELECT t.account_id AS account_id,
       t.anchor_no AS anchor_no,
       t.anchor_balance AS anchor_balance,
       bt.batch_rows AS batch_rows,
       bt.no AS batch_last_no,
       bt.balance AS batch_last_balance,
       fb.no AS break_no,
       fb.kind AS break_kind,
       fb.amount AS break_amount,
       fb.balance AS break_balance,
       fb.chain_prev_no AS break_prev_no,
       fb.chain_prev_balance AS break_prev_balance
FROM targets t
JOIN batch_tail bt ON bt.account_id = t.account_id
LEFT JOIN first_break fb ON fb.account_id = t.account_id
"""
)


class CustomerAccountLedgerVerificationRepositoryImpl(
    CustomerAccountLedgerVerificationRepository
):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_batch(
        self,
        accounts_per_run: int,
        rows_per_account: int,
        max_checkpoint_age_seconds: int,
    ) -> list[CustomerAccountVerification]:
        window_rows = rows_per_account + 1
        result = await self.session.execute(
            _BATCH_SQL,
            {
                "accounts_per_run": accounts_per_run,
                "rows_per_account": rows_per_account,
                "window_rows": window_rows,
                "max_checkpoint_age": max_checkpoint_age_seconds,
            },
        )

        return [
            CustomerAccountVerification(batch_limit=window_rows, **row)
            for row in result.mappings().all()
        ]

    async def add_checkpoint(
        self,
        account_id: UUID,
        through_no: int,
        balance: Decimal,
    ) -> None:
        self.session.add(
            CustomerAccountLedgerVerified(
                account_id=account_id,
                through_no=through_no,
                balance=balance,
                verified_at=datetime.now(UTC),
            )
        )

    async def record_verified(self, verification: CustomerAccountVerification) -> None:
        await self.add_checkpoint(
            account_id=verification.account_id,
            through_no=verification.last_good_no,
            balance=verification.last_good_balance,
        )

    async def record_discrepancy(
        self, verification: CustomerAccountVerification
    ) -> None:
        if verification.break_no is None or verification.break_kind is None:
            raise ValueError("no break to record")

        self.session.add(
            CustomerAccountLedgerDiscrepancy(
                account_id=verification.account_id,
                no=verification.break_no,
                kind=LedgerDiscrepancyKind(verification.break_kind),
                prev_no=verification.break_prev_no or 0,
                expected_balance=verification.expected_balance,
                actual_balance=verification.break_balance or Decimal(0),
                resolved_at=None,
                detected_at=datetime.now(UTC),
            )
        )

    async def resolve_discrepancy(
        self,
        discrepancy_id: int,
        account_id: UUID,
        resolved_by: UUID,
    ) -> None:
        stmt = (
            sa.select(CustomerAccountLedgerDiscrepancy)
            .where(
                CustomerAccountLedgerDiscrepancy.discrepancy_id == discrepancy_id,
                CustomerAccountLedgerDiscrepancy.account_id == account_id,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        discrepancy = result.scalar_one()

        discrepancy.resolved_at = datetime.now(UTC)
        discrepancy.resolved_by = resolved_by

    async def find_open_discrepancy(
        self,
        account_id: UUID,
    ) -> CustomerAccountLedgerDiscrepancyDto | None:
        stmt = sa.select(CustomerAccountLedgerDiscrepancy).where(
            CustomerAccountLedgerDiscrepancy.account_id == account_id,
            CustomerAccountLedgerDiscrepancy.resolved_at.is_(None),
        )
        result = await self.session.execute(stmt)

        discrepancy = result.scalar_one_or_none()
        if discrepancy is None:
            return None

        return CustomerAccountLedgerDiscrepancyDto(
            discrepancy_id=discrepancy.discrepancy_id,
            account_id=discrepancy.account_id,
            no=discrepancy.no,
            kind=discrepancy.kind.value,
            prev_no=discrepancy.prev_no,
            expected_balance=discrepancy.expected_balance,
            actual_balance=discrepancy.actual_balance,
            detected_at=discrepancy.detected_at,
            resolved_at=discrepancy.resolved_at,
            resolved_by=discrepancy.resolved_by,
        )

    async def find_latest_checkpoint(
        self,
        account_id: UUID,
    ) -> CustomerAccountLedgerVerifiedDto | None:
        stmt = (
            sa.select(CustomerAccountLedgerVerified)
            .where(CustomerAccountLedgerVerified.account_id == account_id)
            .order_by(CustomerAccountLedgerVerified.through_no.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)

        checkpoint = result.scalar_one_or_none()
        if checkpoint is None:
            return None

        return CustomerAccountLedgerVerifiedDto(
            account_id=checkpoint.account_id,
            through_no=checkpoint.through_no,
            balance=checkpoint.balance,
            verified_at=checkpoint.verified_at,
        )

    async def find_ledger_balance(
        self,
        account_id: UUID,
        no: int,
    ) -> Decimal | None:
        stmt = sa.select(CustomerAccountLedger.balance).where(
            CustomerAccountLedger.account_id == account_id,
            CustomerAccountLedger.no == no,
        )
        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()
