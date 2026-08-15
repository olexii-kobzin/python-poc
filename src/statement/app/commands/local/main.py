from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import Field

from statement.app.messages_base import BaseAsyncMessage
from statement.domain.entities.account import LedgerOperationType

class CreatePayment(BaseAsyncMessage):
    id: UUID
    account_id: UUID
    type: LedgerOperationType
    signed_amount: Annotated[Decimal, Field(decimal_places=2)]
    occurred_at: datetime

    @classmethod
    def route(cls) -> str:
        return "payment.create"

    def dedupe_key(self) -> str:
        return f"{self.route()}.{str(self.id)}"
