from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement


class DbTestUtil:
    _metadata: ClassVar[sa.MetaData] = sa.MetaData()
    _reflected: ClassVar[set[str]] = set()
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def table(cls, session: AsyncSession, table_name: str) -> sa.Table:
        if table_name in cls._reflected:
            t = cls._metadata.tables.get(table_name)
            if t is not None:
                return t

        async with cls._lock:
            if table_name not in cls._reflected:
                connection = await session.connection()

                def _reflect(sync_connection: sa.Connection) -> None:
                    cls._metadata.reflect(bind=sync_connection, only=[table_name])

                await connection.run_sync(_reflect)
                cls._reflected.add(table_name)

        table = cls._metadata.tables.get(table_name)
        if table is None:
            raise ValueError(f"Unknown table: {table_name}")
        return table

    @staticmethod
    def _build_clause(table: sa.Table, filters: dict[str, Any]) -> ColumnElement[bool]:
        conditions: list[ColumnElement[bool]] = []

        for key, value in filters.items():
            if "__" in key:
                field, operator = key.split("__", 1)
            else:
                field, operator = key, "eq"

            if field not in table.c:
                raise ValueError(f"Unknown column '{field}' in table '{table.name}'")

            column = table.c[field]

            if operator == "eq":
                conditions.append(column == value)
            elif operator == "ne":
                conditions.append(column != value)
            elif operator == "in":
                if not isinstance(value, (list, tuple, set)):
                    raise ValueError(f"{key} expects list/tuple/set")
                conditions.append(column.in_(list(value)))
            elif operator == "isnull":
                conditions.append(column.is_(None) if value else column.is_not(None))
            else:
                raise ValueError(f"Unsupported operator: {operator}")

        return sa.and_(*conditions) if conditions else sa.true()

    @classmethod
    async def count(
        cls,
        session: AsyncSession,
        table_name: str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        table = await cls.table(session, table_name)
        where_clause = cls._build_clause(table, filters or {})
        stmt = sa.select(sa.func.count()).select_from(table).where(where_clause)
        return int((await session.execute(stmt)).scalar_one())

    @classmethod
    async def exists(
        cls,
        session: AsyncSession,
        table_name: str,
        filters: dict[str, Any],
    ) -> bool:
        return (await cls.count(session, table_name, filters)) > 0

    @classmethod
    async def missing(
        cls,
        session: AsyncSession,
        table_name: str,
        filters: dict[str, Any],
    ) -> bool:
        return not await cls.exists(session, table_name, filters)
