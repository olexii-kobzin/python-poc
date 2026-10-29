import structlog
from structlog.contextvars import merge_contextvars
from structlog.typing import EventDict

from statement.infra.observability import _add_service, build_shared_processors


def run_processor(processor: structlog.typing.Processor) -> EventDict:
    result = processor(None, "info", {"event": "something happened"})
    assert isinstance(result, dict)

    return result


def test_add_service_stamps_the_service_name() -> None:
    event = run_processor(_add_service("statement-api"))

    assert event == {"event": "something happened", "service": "statement-api"}


def test_shared_processors_stamp_their_own_service_name() -> None:
    services = []
    for name in ("statement-api", "statement-consumers"):
        stamp = build_shared_processors(name)[-1]
        services.append(run_processor(stamp)["service"])

    assert services == ["statement-api", "statement-consumers"]


def test_shared_processors_merge_bound_context() -> None:
    """request_id bound by the API middleware / job executor reaches every log line."""
    assert merge_contextvars in build_shared_processors("statement-api")
