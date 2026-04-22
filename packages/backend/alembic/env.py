"""Alembic 환경 — SQLAlchemy async 엔진 대응.

``alembic.ini`` 의 ``sqlalchemy.url`` 은 비워두고, 실제 URL 은 런타임에
``app.config.settings.async_database_url`` 로 주입한다.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 모든 모델이 Base.metadata 에 등록되도록 import
from app.config import settings
from app.models import Base  # noqa: F401

# Alembic Config 객체
config = context.config

# 런타임 URL 주입
config.set_main_option("sqlalchemy.url", settings.async_database_url)

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """라이브 DB 에 연결하여 마이그레이션 실행."""
    asyncio.run(run_async_migrations())


def run_migrations_offline() -> None:
    """URL 만 알고 connection 은 맺지 않는 SQL 출력 모드."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
