import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import UrlMapping
from app.schema import create_schema

TEST_SHORT_CODES = ("guide-K7m2Qx9B", "duplicate-A1b2C3d4")


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_engine(database_url)
    create_schema(engine)
    with engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.delete().where(
                UrlMapping.short_code.in_(TEST_SHORT_CODES)
            )
        )

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                UrlMapping.__table__.delete().where(
                    UrlMapping.short_code.in_(TEST_SHORT_CODES)
                )
            )
        engine.dispose()


@pytest.mark.integration
def test_url_mapping_schema_can_be_created(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)

    assert inspector.has_table("url_mappings")
    assert {column["name"] for column in inspector.get_columns("url_mappings")} == {
        "id",
        "short_code",
        "original_url",
        "redirect_count",
        "last_accessed_at",
        "created_at",
    }


@pytest.mark.integration
def test_mapping_is_readable_in_a_fresh_session(postgres_engine: Engine) -> None:
    session_factory = sessionmaker(postgres_engine)
    short_code = "guide-K7m2Qx9B"
    original_url = "https://example.com/guide"
    mapping = UrlMapping(
        short_code=short_code,
        original_url=original_url,
    )

    with session_factory() as write_session:
        write_session.add(mapping)
        write_session.commit()

    with session_factory() as read_session:
        persisted = read_session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == short_code)
        )

    assert persisted is not None
    assert persisted.original_url == original_url
    assert persisted.created_at is not None
    assert persisted.created_at.tzinfo is not None


@pytest.mark.integration
def test_duplicate_short_code_is_rejected_by_postgresql(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(postgres_engine)
    first = UrlMapping(
        short_code="duplicate-A1b2C3d4",
        original_url="https://example.com/first",
    )
    duplicate = UrlMapping(
        short_code=first.short_code,
        original_url="https://example.com/second",
    )

    with session_factory() as session:
        session.add(first)
        session.commit()
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
