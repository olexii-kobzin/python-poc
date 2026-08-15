from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import Field

from statement.app.messages_base import BaseInboundDistributedMessage


class CustomerCreated(BaseInboundDistributedMessage):
    id: UUID
    email: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def route(cls) -> str:
        return "customer.created"


class PaymentEvent(BaseInboundDistributedMessage):
    id: UUID
    account_id: UUID
    amount: Annotated[Decimal, Field(gt=0, decimal_places=2)]
    occurred_at: datetime


class PaymentDeposited(PaymentEvent):
    @classmethod
    def route(cls) -> str:
        return "payment.deposited"


class PaymentWithdrawn(PaymentEvent):
    @classmethod
    def route(cls) -> str:
        return "payment.withdrawn"
