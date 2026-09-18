from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
from app.models import *  # noqa: F401,F403  ensures all models are registered on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# PostGIS/tiger-geocoder extensions create many tables not managed by our models.
# Restrict autogenerate's object comparison to schemas/tables we actually own.
_POSTGIS_SCHEMAS = {"tiger", "tiger_data", "topology"}
_POSTGIS_TABLES = {
    "spatial_ref_sys",
    "layer",
    "topology",
    "geocode_settings",
    "geocode_settings_default",
    "direction_lookup",
    "secondary_unit_lookup",
    "state_lookup",
    "street_type_lookup",
    "place_lookup",
    "county_lookup",
    "countysub_lookup",
    "zip_lookup",
    "zip_lookup_all",
    "zip_lookup_base",
    "zip_state",
    "zip_state_loc",
    "loader_platform",
    "loader_variables",
    "loader_lookuptables",
    "pagc_gaz",
    "pagc_lex",
    "pagc_rules",
    "featnames",
    "addr",
    "addrfeat",
    "edges",
    "faces",
    "place",
    "cousub",
    "county",
    "state",
    "tabblock",
    "tabblock20",
    "tract",
    "bg",
    "zcta5",
}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in _POSTGIS_TABLES:
        return False
    if getattr(object, "schema", None) in _POSTGIS_SCHEMAS:
        return False
    return True


def run_migrations_offline() -> None:
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
