from typing import Any

from sqlalchemy import (
    Select,
    SQLColumnExpression,
    UnaryExpression,
    and_,
    asc,
    desc,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app.repository import CustomerAccountReadRepository
from statement.app.schemas.account import (
    CustomerAccountDisplay,
    CustomerAccountListQuery,
    CustomerAccountListQueryCursor,
    SortField,
)
from statement.app.schemas.base import SortDirection
from statement.domain.entities.account import CustomerAccount


def build_cursor_condition(
    ordering: tuple[tuple[SQLColumnExpression[Any], SortDirection], ...],
    cursor_values: tuple[Any, ...],
) -> SQLColumnExpression[bool]:
    alternatives: list[SQLColumnExpression[bool]] = []

    for index, ((column, direction), cursor_value) in enumerate(
        zip(ordering, cursor_values, strict=True)
    ):
        preceding_equalities = [
            preceding_column == preceding_value
            for (preceding_column, _), preceding_value in zip(
                ordering[:index],
                cursor_values[:index],
                strict=True,
            )
        ]

        comparison = (
            column > cursor_value
            if direction is SortDirection.ASC
            else column < cursor_value
        )

        alternatives.append(and_(*preceding_equalities, comparison))

    return or_(*alternatives)


class CustomerAccountReadRepositoryImpl(CustomerAccountReadRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(
        self,
        query: CustomerAccountListQuery,
    ) -> tuple[list[CustomerAccountDisplay], CustomerAccountListQueryCursor | None]:
        order_columns: dict[SortField | str, SQLColumnExpression[Any]] = {
            SortField.CURRENCY: CustomerAccount.currency,
            SortField.STATUS: CustomerAccount.status,
            SortField.CREATED_AT: CustomerAccount.created_at,
        }
        order_clauses: list[UnaryExpression[Any]] = []
        cursor_ordering: tuple[tuple[SQLColumnExpression[Any], SortDirection], ...] = ()
        cursor_values: tuple[Any, ...] = ()

        limit: int = query.count or 20
        cursor_values_by_field = query.cursor.model_dump() if query.cursor else {}

        stmt: Select[Any] = select(
            CustomerAccount.id,
            CustomerAccount.customer_id,
            CustomerAccount.currency,
            CustomerAccount.name,
            CustomerAccount.status,
            CustomerAccount.created_at,
            CustomerAccount.updated_at,
            CustomerAccount.updated_by,
        ).limit(limit)

        cursor_accepted = True
        sort_fields = []
        for request in query.sort:
            if request.field not in order_columns:
                continue
            field_name = request.field.value
            sort_fields.append(field_name)
            column = order_columns[field_name]
            clause = desc(column) if request.dir == SortDirection.DESC else asc(column)
            order_clauses.append(clause)

            if (
                query.cursor is None
                or field_name not in cursor_values_by_field
                or (
                    field_name in cursor_values_by_field
                    and cursor_values_by_field[field_name] is None
                )
            ):
                cursor_accepted = False
                continue

            cursor_ordering += ((column, request.dir),)
            cursor_values += (cursor_values_by_field[field_name],)

        order_clauses.append(CustomerAccount.id.desc())
        stmt = stmt.order_by(*order_clauses)

        if cursor_accepted and (query.cursor is None or query.cursor.id is None):
            cursor_accepted = False
        elif cursor_accepted and query.cursor:
            cursor_ordering += ((CustomerAccount.id, SortDirection.DESC),)
            cursor_values += (query.cursor.id,)

        if cursor_accepted:
            stmt = stmt.where(build_cursor_condition(cursor_ordering, cursor_values))

        if query.name is not None:
            stmt = stmt.where(CustomerAccount.name.like(f"%{query.name}%"))

        if query.currency is not None:
            stmt = stmt.where(CustomerAccount.currency == query.currency)

        if query.status is not None:
            stmt = stmt.where(CustomerAccount.status == query.status)

        if query.created_at_from is not None:
            stmt = stmt.where(CustomerAccount.created_at >= query.created_at_from)

        if query.created_at_to is not None:
            stmt = stmt.where(CustomerAccount.created_at < query.created_at_to)

        result = await self.session.execute(stmt)

        mappings = result.mappings().all()
        mapped = [CustomerAccountDisplay.model_validate(row) for row in mappings]

        next_cursor = None
        if len(mapped) == limit:
            cursor_row = mapped[-1]
            next_cursor = CustomerAccountListQueryCursor(
                currency=cursor_row.currency if "currency" in sort_fields else None,
                status=cursor_row.status if "status" in sort_fields else None,
                created_at=cursor_row.created_at
                if "created_at" in sort_fields
                else None,
                id=cursor_row.id,
            )

        return mapped, next_cursor
