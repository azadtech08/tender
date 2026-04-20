"""Alembic environment configuration.

This script is run whenever Alembic processes a migration script.
It configures the database connection and target metadata for migrations.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# Import all models for auto-migration detection
# This ensures Alembic sees all tables and fields
from db_models import Base  # noqa: F401
from db_models.user import User  # noqa: F401
from db_models.job import Job  # noqa: F401
from db_models.job_event import JobEvent  # noqa: F401
from db_models.tender import Tender  # noqa: F401
from db_models.schedule import Schedule  # noqa: F401

# This is the Alembic Config object, which provides the values of the
# [alembic] section of the alembic.ini file as Python attributes
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata from imports
target_metadata = Base.metadata

# Get database URL from environment
database_url = os.getenv("SYNC_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    This configures the context with just a URL and not an Engine, though an Engine
    is acceptable here as well.  By skipping the create_engine() call we don't even
    need a DBAPI to be available.
    
    Calls to context.execute() here emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    
    In this scenario we need to create an Engine and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = os.getenv(
        "SYNC_DATABASE_URL",
        configuration.get("sqlalchemy.url", ""),
    )
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.StaticPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
