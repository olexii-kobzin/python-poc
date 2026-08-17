from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    sub: UUID
    scopes: frozenset[str]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
