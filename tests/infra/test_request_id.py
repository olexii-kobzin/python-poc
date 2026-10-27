import uuid

import pytest
from structlog.contextvars import bound_contextvars

from statement.infra.request_id import (
    REQUEST_ID_HEADER,
    propagation_headers,
    request_id_from,
    resolve_request_id,
)


def test_valid_uuid_is_kept() -> None:
    raw = str(uuid.uuid7())

    assert resolve_request_id(raw) == raw


def test_valid_uuid_is_normalized() -> None:
    raw = uuid.uuid4()

    assert resolve_request_id(str(raw).upper()) == str(raw)


@pytest.mark.parametrize("raw", [None, "", "not-a-uuid", "x" * 500, 42, b"bytes"])
def test_invalid_value_is_replaced_with_a_new_uuid(raw: object) -> None:
    resolved = resolve_request_id(raw)

    assert str(uuid.UUID(resolved)) == resolved
    assert resolved != raw


def test_request_id_from_headers() -> None:
    raw = str(uuid.uuid7())

    assert request_id_from({REQUEST_ID_HEADER: raw}) == raw


@pytest.mark.parametrize("headers", [None, {}, {"other": "x"}])
def test_request_id_from_missing_header_generates_one(
    headers: dict[str, object] | None,
) -> None:
    resolved = request_id_from(headers)

    assert str(uuid.UUID(resolved)) == resolved


def test_propagation_headers_empty_when_nothing_is_bound() -> None:
    assert propagation_headers() is None


def test_propagation_headers_carry_the_bound_id() -> None:
    raw = str(uuid.uuid7())

    with bound_contextvars(request_id=raw):
        assert propagation_headers() == {REQUEST_ID_HEADER: raw}

    assert propagation_headers() is None
