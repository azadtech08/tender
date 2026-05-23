"""Database session factory and FastAPI dependencies."""

from typing import AsyncGenerator, Optional

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from db_models import Base

engine = create_async_engine(
    settings.database_url.strip(),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Plain DB session — no RLS.  Use only for health checks and migrations."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db_rls(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """DB session with Postgres RLS activated for the current tenant.

    Sets `app.tenant_id` as a session-local variable inside a transaction so
    that all queries in the same request are automatically scoped by the
    tenant_isolation RLS policy (migration 003).

    Usage in route:
        db: AsyncSession = Depends(get_db_rls)
    """
    tenant_id: Optional[str] = getattr(request.state, "tenant_id", None)

    async with async_session() as session:
        async with session.begin():
            # SET LOCAL is transaction-scoped — reset when transaction ends.
            safe_tid = (tenant_id or "").replace("'", "''")
            await session.execute(
                text(f"SET LOCAL app.tenant_id = '{safe_tid}'")
            )
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            # Commit happens automatically when the `begin()` context exits.


async def create_tables() -> None:
    """Create all ORM-mapped tables (dev only; prod uses Alembic migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
