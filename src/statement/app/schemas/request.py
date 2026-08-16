from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from statement.app.schemas.base import SortDirection


class InvalidPaginationCursor(ValueError):
    pass


class PaginatedQuery[T](BaseModel):
    cursor: T | None = None
    count: Annotated[int | None, Field(ge=1, le=100)] = None


class SortRequest[T: StrEnum](BaseModel):
    field: T
    dir: SortDirection


class SortQuery[T: StrEnum](BaseModel, ABC):
    sort: tuple[SortRequest[T], ...] = Field(
        default=None,
        validate_default=True,
    )

    @classmethod
    @abstractmethod
    def _default_sort(cls) -> SortRequest[T]: ...

    @field_validator("sort", mode="before")
    @classmethod
    def parse_sort(cls, value: Any) -> Any:
        parsed: list[dict[str, str]] = []

        if value is None:
            default = cls._default_sort()
            parsed.append(
                {
                    "field": default.field,
                    "dir": default.dir.value,
                }
            )
            return parsed

        if not isinstance(value, (list, tuple)):
            value = [value]

        for item in value:
            if not isinstance(item, str):
                raise ValueError("Each sort value must be a string")

            field, separator, direction = item.partition(":")
            if not separator or not field or not direction:
                raise ValueError("Sort must use the format '<field>:<asc|desc>'")

            parsed.append(
                {
                    "field": field,
                    "dir": direction,
                }
            )

        return parsed
