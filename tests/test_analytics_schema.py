import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Engine,
    Identity,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    select,
)
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.models import Base, UrlMapping
from app.schema import apply_schema_migrations, create_schema


@pytest.fixture
def isolated_postgres_engine() -> Iterator[Engine]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")

    schema_name = f"task8_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema_name))

    engine = create_engine(
        database_url,
        connect_args={"options": f"-csearch_path={schema_name}"},
    )

    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema_name, cascade=True))
        admin_engine.dispose()


@pytest.mark.integration
def test_fresh_mapping_has_analytics_defaults(
    isolated_postgres_engine: Engine,
) -> None:
    create_schema(isolated_postgres_engine)

    with Session(isolated_postgres_engine, expire_on_commit=False) as session:
        mapping = UrlMapping(
            short_code="analytics-fresh-A1b2C3d4",
            original_url="https://example.com/fresh",
        )
        session.add(mapping)
        session.commit()

    assert mapping.redirect_count == 0
    assert mapping.last_accessed_at is None


@pytest.mark.integration
def test_migration_preserves_phase_one_rows_and_is_repeatable(
    isolated_postgres_engine: Engine,
) -> None:
    phase_one_metadata = MetaData()
    phase_one_table = Table(
        "url_mappings",
        phase_one_metadata,
        Column("id", BigInteger, Identity(), primary_key=True),
        Column("short_code", String(64), nullable=False, unique=True),
        Column("original_url", Text, nullable=False),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    phase_one_metadata.create_all(isolated_postgres_engine)
    with isolated_postgres_engine.begin() as connection:
        connection.execute(
            phase_one_table.insert().values(
                short_code="analytics-existing-A1b2C3d4",
                original_url="https://example.com/existing",
            )
        )

    apply_schema_migrations(isolated_postgres_engine)
    apply_schema_migrations(isolated_postgres_engine)

    columns = {
        column["name"]: column
        for column in inspect(isolated_postgres_engine).get_columns("url_mappings")
    }
    with Session(isolated_postgres_engine) as session:
        existing = session.scalar(
            select(UrlMapping).where(
                UrlMapping.short_code == "analytics-existing-A1b2C3d4"
            )
        )

    assert columns["redirect_count"]["nullable"] is False
    assert columns["last_accessed_at"]["nullable"] is True
    assert existing is not None
    assert existing.original_url == "https://example.com/existing"
    assert existing.redirect_count == 0
    assert existing.last_accessed_at is None


def test_model_metadata_includes_analytics_columns() -> None:
    table = Base.metadata.tables["url_mappings"]

    assert table.c.redirect_count.server_default is not None
    assert table.c.redirect_count.nullable is False
    assert table.c.last_accessed_at.server_default is None
    assert table.c.last_accessed_at.nullable is True
