import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from backend.core.config import settings
from backend.database.base import Base
import backend.models.user_model       # noqa
import backend.models.incident_model   # noqa
import backend.models.runbook_model    # noqa
import backend.models.topology_model   # noqa

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: context.configure(connection=c, target_metadata=target_metadata, compare_type=True)
        )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: context.run_migrations())
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
