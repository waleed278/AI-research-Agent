from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit naming convention so Alembic autogenerate produces stable,
# predictable constraint/index names instead of dialect-generated ones that
# differ across environments and make migration diffs noisy.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every `Mapped[datetime]` column is TIMESTAMPTZ, not the Postgres
    # default TIMESTAMP WITHOUT TIME ZONE -- application code stores
    # timezone-aware UTC datetimes (`datetime.now(UTC)`) everywhere, and a
    # naive column silently rejects those at the driver level.
    type_annotation_map = {datetime: DateTime(timezone=True)}
