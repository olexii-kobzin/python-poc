import uuid
from collections.abc import Mapping

from structlog.contextvars import get_contextvars

REQUEST_ID_HEADER = "x-request-id"


def resolve_request_id(raw: object) -> str:
    if isinstance(raw, str):
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            pass

    return str(uuid.uuid7())


def request_id_from(headers: Mapping[str, object] | None) -> str:
    return resolve_request_id((headers or {}).get(REQUEST_ID_HEADER))


def propagation_headers() -> dict[str, str] | None:
    request_id = get_contextvars().get("request_id")
    if request_id is None:
        return None

    return {REQUEST_ID_HEADER: str(request_id)}
