from abc import ABC, abstractmethod
from typing import Self

from pydantic import BaseModel, ConfigDict


class BaseInboundDistributedMessage(BaseModel, ABC):
    model_config = ConfigDict(frozen=True)

    @classmethod
    @abstractmethod
    def route(cls) -> str: ...


class BaseOutgoingDistributedMessage(BaseModel, ABC):
    model_config = ConfigDict(frozen=True)

    @classmethod
    @abstractmethod
    def route(cls) -> str: ...

    def to_payload_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


class BaseAsyncMessage(BaseModel, ABC):
    @classmethod
    @abstractmethod
    def route(cls) -> str: ...

    @abstractmethod
    def dedupe_key(self) -> str: ...

    @classmethod
    def from_payload_bytes(cls, payload: bytes | None) -> Self | None:
        if payload is None:
            return None

        return cls.model_validate_json(payload)

    def to_payload_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")
