from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings, sqlalchemy_database_url
from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

if context.is_offline_mode():
    context.configure(
        url=sqlalchemy_database_url(get_settings().database_url),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        context.configure(
            connection=provided_connection,
            target_metadata=Base.metadata,
            version_table_schema=config.attributes.get("version_table_schema"),
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(sqlalchemy_database_url(get_settings().database_url))
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
