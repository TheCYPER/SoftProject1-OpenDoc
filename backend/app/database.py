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
        # Lightweight schema evolution for the PoC's SQLite-first setup.
        tables_to_columns = {
            "documents": {
                "yjs_state": "BLOB",
            },
            "ai_interactions": {
                "provider_name": "VARCHAR(50)",
                "model_name": "VARCHAR(100)",
                "prompt_text": "TEXT",
                "system_prompt_text": "TEXT",
                "error_code": "VARCHAR(100)",
                "error_message": "VARCHAR(500)",
            },
            "ai_suggestions": {
                "partial_output_available": "BOOLEAN NOT NULL DEFAULT 0",
            },
        }

        for table_name, columns in tables_to_columns.items():
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing_columns = {row[1] for row in result.fetchall()}
            for column_name, column_sql in columns.items():
                if column_name not in existing_columns:
                    await conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
                    )


async def get_async_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
