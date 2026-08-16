from datetime import UTC, datetime

import structlog
from pgqueuer import PgQueuer
from pgqueuer.models import Schedule, ScheduleContext

from statement.conf import settings
from statement.infra.repository.ledger_verification import (
    CustomerAccountLedgerVerificationRepositoryImpl,
)

log = structlog.get_logger(__name__)


def register_jobs(pgq: PgQueuer) -> None:
    @pgq.schedule("interval", expression="* * * * * */15", clean_old=True)
    async def interval(schedule: Schedule) -> None:
        print(datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"))

    @pgq.schedule(
        "customer_account_ledger_verify",
        expression="*/5 * * * *",
        clean_old=True,
    )
    async def verify_customer_account_ledger(
        schedule: Schedule,
        ctx: ScheduleContext,
    ) -> None:
        session_scope = ctx.resources["session_scope"]

        async with session_scope() as session:
            repo = CustomerAccountLedgerVerificationRepositoryImpl(session=session)

            batch = await repo.next_batch(
                accounts_per_run=settings.ledger_verify_accounts_per_run,
                rows_per_account=settings.ledger_verify_rows_per_account,
                max_checkpoint_age_seconds=(
                    settings.ledger_verify_max_checkpoint_age_seconds
                ),
            )

            discrepancies: int = 0
            checkpoints: int = 0
            for verification in batch:
                if verification.break_kind is not None:
                    discrepancies += 1
                    log.warning(
                        "customer_account_ledger.discrepancy",
                        details={
                            "account_id": str(verification.account_id),
                            "kind": verification.break_kind,
                            "no": verification.break_no,
                            "prev_no": verification.break_prev_no,
                            "expected_balance": str(verification.expected_balance),
                            "actual_balance": str(verification.break_balance),
                            "verified_through_no": verification.anchor_no,
                        },
                    )
                    repo.record_discrepancy(verification)

                if verification.should_checkpoint:
                    checkpoints += 1
                    repo.record_verified(verification)

            await session.commit()

        log.info(
            "customer_account_ledger.verified",
            details={
                "accounts": len(batch),
                "checkpoints": checkpoints,
                "discrepancies": discrepancies,
            },
        )
