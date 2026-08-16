from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn

from pgqueuer import errors, models
from pgqueuer.core.executors import EntrypointExecutor

from statement.app.errors.main import LastAttemptError, TerminalJobError

OnLastAttempt = Callable[[models.Job, models.Context, Exception], Awaitable[None]]


@dataclass
class DlqRetryEntrypointExecutor(EntrypointExecutor):
    max_attempts: int = 3
    initial_delay: timedelta = timedelta(milliseconds=200)
    max_delay: timedelta = timedelta(minutes=1)
    backoff_multiplier: float = 5.0
    on_last_attempt: OnLastAttempt | None = None

    async def execute(self, job: models.Job, context: models.Context) -> None:
        try:
            await super().execute(job, context)
        except TerminalJobError as e:
            await self._fail(job, context, e)
        except Exception as e:
            if job.attempts >= self.max_attempts:
                await self._fail(job, context, e)
            delay = min(
                self.initial_delay * (self.backoff_multiplier**job.attempts),
                self.max_delay,
                )
            raise errors.RetryRequested(delay=delay, reason=str(e)) from e

    async def _fail(
        self,
        job: models.Job,
        context: models.Context,
        e: Exception,
    ) -> NoReturn:
        if self.on_last_attempt:
            await self.on_last_attempt(job, context, e)
        raise LastAttemptError(str(e)) from e
