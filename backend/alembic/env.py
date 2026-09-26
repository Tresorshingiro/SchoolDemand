"""Alembic migrations for the school planning database (models in app/models.py)."""
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registers the tables)
from app.config import settings
from app.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.url.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def include_object(obj, name, type_, reflected, compare_to):
    """Only our tables: the PostGIS image also ships tiger geocoder / topology tables, which must never be dropped."""
    if type_ == "table" and reflected and compare_to is None:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


# PostGIS: keep its own tables out of autogenerate and render geometry columns / spatial indexes properly
common = dict(
    target_metadata=Base.metadata,
    include_object=include_object,
    process_revision_directives=alembic_helpers.writer,
    render_item=alembic_helpers.render_item,
    compare_type=True,
)


def run_migrations_offline() -> None:
    context.configure(url=settings.url, literal_binds=True, dialect_opts={"paramstyle": "named"}, **common)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, **common)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
