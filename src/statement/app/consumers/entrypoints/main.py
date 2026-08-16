from datetime import timedelta

import structlog
from pgqueuer import PgQueuer, RetryRequested
from pgqueuer.models import Context, Job
from pydantic import ValidationError

from statement.app.commands.local.main import CreatePayment
from statement.app.consumers.executor import DlqRetryEntrypointExecutor
from statement.app.errors.main import TerminalJobError
from statement.app.events.distributed.outgoing.main import (
    CustomerAccountCreated as CustomerAccountCreatedOutgoing,
)
from statement.app.events.local.main import CustomerAccountCreated
from statement.app.messages_base import BaseAsyncMessage
from statement.app.subscribers.base import events_exchange
from statement.domain.entities.account import (
    CustomerAccountLedger,
    CustomerAccountStatus,
)
from statement.infra.repository.account import CustomerAccountRepositoryImpl

_PAYLOAD_LOG_LIMIT = 200

log = structlog.get_logger(__name__)


def _payload_preview(payload: bytes | None) -> str | None:
    if not payload:
        return None
    return payload[:_PAYLOAD_LOG_LIMIT].decode("utf-8", errors="replace")


def _decode_or_fail[T: BaseAsyncMessage](message_cls: type[T], job: Job) -> T:
    reason = "empty payload"
    try:
        event = message_cls.from_payload_bytes(job.payload)
    except ValidationError as e:
        event = None
        reason = str(e)

    if event is None:
        log.warning(
            "consumer.undecodable_payload",
            details={
                "entrypoint": job.entrypoint,
                "job_id": int(job.id),
                "payload_size": len(job.payload) if job.payload else 0,
                "payload": _payload_preview(job.payload),
            },
        )
        raise TerminalJobError(
            f"Undecodable payload for {job.entrypoint}: {reason}",
        )

    return event


def register_entrypoints(pgq: PgQueuer) -> None:
    async def on_job_last_attempt(
        job: Job,
        context: Context,
        err: Exception,
    ) -> None:
        log.error(
            f"Consumer job {job.entrypoint} exhausted",
            details={
                "entrypoint": job.entrypoint,
                "job_id": int(job.id),
                "attempts": job.attempts,
                "error_type": type(err).__name__,
                "error": str(err),
                "reason": getattr(err, "reason", None),
            },
        )

    @pgq.entrypoint(
        CustomerAccountCreated.route(),
        on_failure="hold",
        executor_factory=lambda params: DlqRetryEntrypointExecutor(
            parameters=params,
            max_attempts=3,
            initial_delay=timedelta(milliseconds=200),
            max_delay=timedelta(minutes=1),
            backoff_multiplier=5.0,
            on_last_attempt=on_job_last_attempt,
        ),
    )
    async def on_customer_account_created(job: Job, ctx: Context) -> None:
        event = _decode_or_fail(CustomerAccountCreated, job)

        broker = ctx.resources["broker"]

        outgoing_event = CustomerAccountCreatedOutgoing(
            id=event.id,
            customer_id=event.customer_id,
            currency=event.currency,
            name=event.name,
            status=event.status,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

        await broker.publish(
            outgoing_event.to_payload_bytes(),
            routing_key=outgoing_event.route(),
            exchange=events_exchange,
            content_encoding="utf-8",
            content_type="application/json",
        )

        return None

    @pgq.entrypoint(
        CreatePayment.route(),
        on_failure="hold",
        executor_factory=lambda params: DlqRetryEntrypointExecutor(
            parameters=params,
            max_attempts=3,
            initial_delay=timedelta(milliseconds=200),
            max_delay=timedelta(minutes=1),
            backoff_multiplier=5.0,
            on_last_attempt=on_job_last_attempt,
        ),
    )
    async def on_create_payment(job: Job, ctx: Context) -> None:
        session_scope = ctx.resources["session_scope"]
        event = _decode_or_fail(CreatePayment, job)

        async with session_scope() as session:
            repo = CustomerAccountRepositoryImpl(session=session)

            account = await repo.lock_by_id(event.account_id)
            if account is None:
                log.warning(
                    "customer_account_ledger.unknown_account",
                    details={
                        "account_id": str(event.account_id),
                        "operation_id": str(event.id),
                    },
                )
                raise RetryRequested(
                    reason=f"Account {event.account_id} is not found",
                )

            if account.status != CustomerAccountStatus.ACTIVE:
                log.warning(
                    "customer_account_ledger.account_not_active",
                    details={
                        "account_id": str(event.account_id),
                        "operation_id": str(event.id),
                        "status": account.status,
                    },
                )
                raise TerminalJobError(f"Account {event.account_id} is not active")

            if await repo.has_ledger_operation(event.account_id, event.id):
                log.info(
                    "customer_account_ledger.duplicate_operation",
                    details={
                        "account_id": str(event.account_id),
                        "operation_id": str(event.id),
                    },
                )
                return None

            previous = await repo.find_last_ledger_entry(event.account_id)
            if previous is None:
                log.warning(
                    "customer_account_ledger.not_found",
                    details={
                        "account_id": str(event.account_id),
                        "operation_id": str(event.id),
                    },
                )
                raise TerminalJobError(
                    f"Customer account ledger {event.account_id} is not found",
                )

            balance_after = previous.balance + event.signed_amount
            if balance_after < 0:
                log.warning(
                    "customer_account_ledger.insufficient_balance",
                    details={
                        "account_id": str(event.account_id),
                        "operation_id": str(event.id),
                        "balance": str(previous.balance),
                        "amount": str(event.signed_amount),
                    },
                )
                raise TerminalJobError(
                    f"Customer account {event.account_id} has insufficient"
                    f" funds for payment {event.id} ({abs(balance_after)})",
                )

            entry = CustomerAccountLedger.follow(
                previous=previous,
                amount=event.signed_amount,
                operation_type=event.type,
                operation_id=event.id,
                created_by=None,
            )
            session.add(entry)
            await session.commit()

        return None
