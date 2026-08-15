from datetime import datetime
from uuid import UUID

from statement.app.messages_base import BaseOutgoingDistributedMessage


class CustomerAccountCreated(BaseOutgoingDistributedMessage):
    id: UUID
    customer_id: UUID
    currency: str
    name: str | None
    status: str
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def route(cls) -> str:
        return "customer-account.created"
