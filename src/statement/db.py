from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session as SyncSession

from statement.conf import AppEnv, settings
from statement.persistence.versioned_history import versioned_session

sa_engine = create_async_engine(
    settings.database_async_url,
    echo=(settings.app_env == AppEnv.LOCAL),
    pool_pre_ping=True,
)


class VersionedSession(SyncSession):
    """Sync Session that AsyncSession proxies internally.

    ORM events fire on this inner session, so the history "before_flush"
    listener is attached here rather than to the async_sessionmaker.
    """


versioned_session(VersionedSession)

Session = async_sessionmaker(
    bind=sa_engine,
    class_=AsyncSession,
    sync_session_class=VersionedSession,
    expire_on_commit=False,
)
