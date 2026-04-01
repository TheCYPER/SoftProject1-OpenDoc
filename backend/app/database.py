from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables (for development/PoC — use Alembic in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate: add yjs_state column if missing on existing databases.
        result = await conn.execute(text("PRAGMA table_info(documents)"))
        columns = {row[1] for row in result.fetchall()}
        if "yjs_state" not in columns:
            await conn.execute(text("ALTER TABLE documents ADD COLUMN yjs_state BLOB"))


async def get_async_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
