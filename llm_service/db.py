"""Async SQLAlchemy engine for the tables FastAPI owns outright
(Conversation/Message) - a real asyncpg driver, not sync_to_async bridging,
since these tables aren't shared with Django's ORM/migrations.
"""

import os
from pathlib import Path

import environ
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Standalone entry points into this module (Alembic's CLI, in particular)
# never go through Django's settings.py, so nothing else loads .env into
# os.environ first - read_env() uses setdefault() internally, so this is a
# harmless no-op on the path where django.setup() already loaded it.
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(BASE_DIR / ".env")


def _database_url() -> str:
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(_database_url(), pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """FastAPI dependency: yields a session, always closed after the request."""
    async with async_session_factory() as session:
        yield session