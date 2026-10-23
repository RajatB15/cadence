from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from cadence_app.models import Base

config = context.config
target_metadata = Base.metadata
database_url = context.get_x_argument(as_dictionary=True).get(
    "db", config.get_main_option("sqlalchemy.url")
)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
