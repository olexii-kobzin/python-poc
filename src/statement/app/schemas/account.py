import base64
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from statement.app import version_token
from statement.app.enums.account import LedgerDiscrepancyKind
from statement.app.schemas.base import SortDirection
from statement.app.schemas.request import PaginatedQuery, SortQuery, SortRequest
from statement.app.schemas.response import FormattedDateTime
from statement.app.schemas.validation import DateTimeRangeMixin
from statement.domain.entities import CustomerAccountStatus
from statement.domain.enum import Currency


class SortField(StrEnum):
    CURRENCY = "currency"
    STATUS = "status"
    CREATED_AT = "created_at"


class CustomerAccountCreate(BaseModel):
    name: Annotated[str, Field(min_length=3, max_length=50)]
    customer_id: UUID
    currency: Currency


class CustomerAccountUpdate(BaseModel):
    version: Annotated[
        str,
        Field(
            min_length=version_token.TOKEN_LENGTH,
            max_length=version_token.TOKEN_LENGTH,
        ),
    ]
    name: Annotated[str | None, Field(min_length=3, max_length=50)] = None
    status: (
        Literal[CustomerAccountStatus.ACTIVE, CustomerAccountStatus.DISABLED] | None
    ) = None


class CustomerAccountDisplay(BaseModel):
    id: UUID
    customer_id: UUID
    currency: Currency
    name: str
    status: CustomerAccountStatus
    created_at: FormattedDateTime
    updated_at: FormattedDateTime
    updated_by: UUID | None
    version: str


class LedgerDiscrepancyDisplay(BaseModel):
    id: UUID
    no: int
    kind: LedgerDiscrepancyKind
    prev_no: int
    expected_balance: Decimal | None
    actual_balance: Decimal
    detected_at: FormattedDateTime
    verified_through_no: int


class LedgerDiscrepancyResolve(BaseModel):
    """Accept the ledger as it stands and checkpoint through ``through_no``.

    This does not repair anything -- it records that a human looked at the
    break and decided the current rows are the truth to move forward from.
    Defaults to the broken row itself, which is the narrowest useful choice.
    """

    through_no: Annotated[int | None, Field(default=None, ge=1)]


class CustomerAccountListQueryCursor(BaseModel):
    currency: Currency | None = None
    status: CustomerAccountStatus | None = None
    created_at: datetime | None = None
    id: UUID

    def encode(self) -> str:
        dump = self.model_dump_json()
        return base64.urlsafe_b64encode(dump.encode("utf-8")).decode("utf-8")

    @classmethod
    def decode(cls, cursor: str) -> Self:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return cls.model_validate_json(decoded)


class CustomerAccountListQuery(
    SortQuery[SortField],
    PaginatedQuery[CustomerAccountListQueryCursor],
    DateTimeRangeMixin,
):
    datetime_range_fields = ("created_at",)

    name: str | None = None
    currency: str | None = None
    status: CustomerAccountStatus | None = None
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None

    @classmethod
    def _default_sort(cls) -> SortRequest[SortField]:
        return SortRequest[SortField](
            field=SortField.CREATED_AT,
            dir=SortDirection.DESC,
        )

    @field_validator("cursor", mode="before")
    @classmethod
    def parse_cursor(cls, value: Any) -> CustomerAccountListQueryCursor | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError("Cursor value must be a string")

        return CustomerAccountListQueryCursor.decode(value)
