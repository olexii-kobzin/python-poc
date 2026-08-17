"""Opaque, tamper-evident tokens for an entity's optimistic-lock version.

Not an authorization boundary -- a caller who may update the resource can
re-read it for a fresh token. It stops a client *fabricating* a version
(hardcoding it, incrementing it locally, retrying with version + 1), each of
which defeats the lock while looking like it works.
"""

import hmac
from base64 import urlsafe_b64encode
from hashlib import sha256
from uuid import UUID

from statement.conf import settings

# 128 bits: forging one costs a brute force over the full space, and the
# attacker gains nothing a plain re-read would not already give them
_DIGEST_BYTES = 16

TOKEN_LENGTH = len(urlsafe_b64encode(b"\x00" * _DIGEST_BYTES).rstrip(b"="))
"""Every token is exactly this long; derived so it tracks _DIGEST_BYTES."""


def issue(entity_id: UUID, version: int) -> str:
    digest = hmac.new(
        settings.version_token_secret.encode("utf-8"),
        f"{entity_id}:{version}".encode(),
        sha256,
    ).digest()[:_DIGEST_BYTES]

    return urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify(entity_id: UUID, version: int, token: str) -> bool:
    """True when ``token`` is the one issued for this entity at this version."""
    return hmac.compare_digest(issue(entity_id, version), token)
