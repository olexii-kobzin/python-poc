import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from statement import fast_deps

router = APIRouter(tags=["system"])

READY_TIMEOUT_SECONDS = 2


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    session: Annotated[AsyncSession, Depends(fast_deps.get_session)],
) -> dict[str, str]:
    try:
        async with asyncio.timeout(READY_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc

    return {"status": "ok"}
