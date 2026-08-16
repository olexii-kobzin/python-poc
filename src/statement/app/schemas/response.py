from datetime import datetime
from typing import Annotated, TypeVar

from pydantic import BaseModel, PlainSerializer

T = TypeVar("T")

FormattedDateTime = Annotated[
    datetime,
    PlainSerializer(
        lambda value: value.isoformat(),
        return_type=str,
        when_used="json",
    ),
]


class InvalidPaginationCursor(ValueError):
    pass


class PaginatedResponseMeta(BaseModel):
    next_cursor: str | None = None


class PaginatedResponse[T](BaseModel):
    data: list[T]
    meta: PaginatedResponseMeta
