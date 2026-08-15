from datetime import UTC, datetime, timedelta

import anyio
import pytest
from pgqueuer import RetryRequested
from pgqueuer.executors import EntrypointExecutorParameters
from pgqueuer.models import Context, Job
from pgqueuer.types import JobId

from statement.app.consumers.executor import DlqRetryEntrypointExecutor
from statement.app.errors.main import LastAttemptError

MAX_ATTEMPTS = 3


def make_job(attempts: int) -> Job:
    now = datetime.now(UTC)
    return Job(
        id=JobId(1),
        priority=0,
        created=now,
        updated=now,
        heartbeat=now,
        execute_after=now,
        status="picked",
        entrypoint="test.entrypoint",
        payload=b"{}",
        attempts=attempts,
        queue_manager_id=None,
        headers=None,
    )


def build_executor(func, calls: list[Exception]) -> DlqRetryEntrypointExecutor:
    async def on_last_attempt(job: Job, context: Context, err: Exception) -> None:
        calls.append(err)

    return DlqRetryEntrypointExecutor(
        parameters=EntrypointExecutorParameters(
            func=func,
            concurrency_limit=0,
            accepts_context=False,
            on_failure="hold",
        ),
        max_attempts=MAX_ATTEMPTS,
        initial_delay=timedelta(microseconds=200),
        max_delay=timedelta(minutes=1),
        backoff_multiplier=5.0,
        on_last_attempt=on_last_attempt,
    )


@pytest.mark.anyio
async def test_success_does_not_touch_the_dlq_hook() -> None:
    calls: list[Exception] = []

    async def ok(job: Job) -> None:
        return None

    await build_executor(ok, calls).execute(
        make_job(attempts=0),
        Context(cancellation=anyio.CancelScope(), resources={}),
    )

    assert calls == []


@pytest.mark.anyio
async def test_failure_within_budget_is_retried_without_the_hook() -> None:
    calls: list[Exception] = []

    async def boom(job: Job) -> None:
        raise RuntimeError("transient")

    executor = build_executor(boom, calls)

    for attempt in range(MAX_ATTEMPTS):
        with pytest.raises(RetryRequested):
            await executor.execute(
                make_job(attempts=attempt),
                Context(cancellation=anyio.CancelScope(), resources={}),
            )

    assert calls == [], "the hook is for the last attempt, not for every failure"


@pytest.mark.anyio
async def test_exhausted_budget_fires_the_hook_and_goes_terminal() -> None:
    calls: list[Exception] = []

    async def failed_job(job: Job) -> None:
        raise RuntimeError("permanent")

    executor = build_executor(failed_job, calls)

    with pytest.raises(LastAttemptError, match="permanent"):
        await executor.execute(
            make_job(attempts=MAX_ATTEMPTS),
            Context(cancellation=anyio.CancelScope(), resources={}),
        )

    assert [str(err) for err in calls] == ["permanent"]
