from datetime import datetime, UTC
from enum import StrEnum
from typing import TYPE_CHECKING, Self
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from statement.domain.entities.base import Base

if TYPE_CHECKING:
    from statement.domain.entities.account import CustomerAccount


class CustomerStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[UUID] = mapped_column(sa.Uuid(), primary_key=True)
    email: Mapped[str] = mapped_column(sa.Text(), unique=True)
    name: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    # TODO: map as enum
    status: Mapped[CustomerStatus] = mapped_column(
        sa.Enum(
            CustomerStatus,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=CustomerStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        index=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    accounts: Mapped[list[CustomerAccount]] = relationship(back_populates="customer")

    @classmethod
    def create(
        cls,
        entity_id: UUID,
        email: str,
        name: str,
        status: CustomerStatus,
        created_at: datetime,
        updated_at: datetime | None,
    ) -> Self:
        return cls(
            id=entity_id,
            email=email,
            name=name,
            status=status.value,
            created_at=created_at,
            updated_at=updated_at,
        )
