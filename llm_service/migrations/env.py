import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from llm_service.db import Base, _database_url
from llm_service import models  # noqa: F401 - registers models on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", _database_url())

target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to) -> bool:
    """This Postgres instance also holds every Django-migrated table
    (users, documents, document_chunks, the old conversations/chat_messages,
    ...). Without this filter, autogenerate diffs the *entire* database
    against Base.metadata (which only knows ai_conversations/ai_messages)
    and proposes dropping every Django table it finds - confirmed this by
    actually running it. Ignore anything reflected from the DB that isn't
    one of our own tables; Django owns those, Alembic must never touch them.
    """
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
