import os
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models import UrlMapping
from app.schema import create_schema
from app.url_creation import (
    MAX_CREATION_ATTEMPTS,
    ShortCodeCollisionError,
    UrlPersistenceError,
    create_url_mapping,
)
from app.url_validation import UrlValidationError

TEST_CODE_PREFIX = "task5-"


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_engine(database_url)
    create_schema(engine)
    _delete_test_mappings(engine)

    try:
        yield engine
    finally:
        _delete_test_mappings(engine)
        engine.dispose()


def _delete_test_mappings(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.delete().where(
                UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%")
            )
        )


def fixed_generator(code: str):
    return lambda original_url: code


@pytest.mark.integration
def test_valid_url_is_committed_and_readable_in_fresh_session(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(postgres_engine, expire_on_commit=False)
    submitted_url = "HTTPS://EXAMPLE.COM/A//guide?b=2&a=1#Section"

    with session_factory() as write_session:
        mapping = create_url_mapping(
            write_session,
            submitted_url,
            code_generator=fixed_generator("task5-guide-A1b2C3d4"),
        )

    with session_factory() as read_session:
        persisted = read_session.scalar(
            select(UrlMapping).where(UrlMapping.id == mapping.id)
        )

    assert mapping.id is not None
    assert mapping.created_at is not None
    assert persisted is not None
    assert persisted.short_code == mapping.short_code
    assert persisted.original_url == ("https://example.com/A//guide?b=2&a=1#Section")


@pytest.mark.integration
def test_collision_retries_and_commits_next_candidate(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(postgres_engine, expire_on_commit=False)
    collision_code = "task5-collision-A1b2C3d4"
    success_code = "task5-success-Z9y8X7w6"
    candidates = iter((collision_code, success_code))

    with session_factory() as session:
        session.add(
            UrlMapping(
                short_code=collision_code,
                original_url="https://example.com/existing",
            )
        )
        session.commit()
        mapping = create_url_mapping(
            session,
            "https://example.com/new",
            code_generator=lambda original_url: next(candidates),
        )

    assert mapping.short_code == success_code
    with session_factory() as fresh_session:
        assert fresh_session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == success_code)
        )


@pytest.mark.integration
def test_five_collisions_raise_controlled_error(postgres_engine: Engine) -> None:
    session_factory = sessionmaker(postgres_engine, expire_on_commit=False)
    collision_codes = [
        f"task5-exhausted{i}-A1b2C3d4" for i in range(MAX_CREATION_ATTEMPTS)
    ]
    candidates = iter(collision_codes)

    with session_factory() as session:
        session.add_all(
            UrlMapping(short_code=code, original_url="https://example.com/existing")
            for code in collision_codes
        )
        session.commit()

        with pytest.raises(ShortCodeCollisionError, match="5 attempts"):
            create_url_mapping(
                session,
                "https://example.com/new",
                code_generator=lambda original_url: next(candidates),
            )

    with session_factory() as fresh_session:
        count = fresh_session.scalar(
            select(func.count())
            .select_from(UrlMapping)
            .where(UrlMapping.short_code.in_(collision_codes))
        )
    assert count == MAX_CREATION_ATTEMPTS


def test_commit_failure_rolls_back_and_never_returns_success() -> None:
    session = Mock(spec=Session)
    session.commit.side_effect = SQLAlchemyError("internal database detail")

    with pytest.raises(UrlPersistenceError) as captured_error:
        create_url_mapping(
            session,
            "https://example.com/guide",
            code_generator=fixed_generator("task5-failure-A1b2C3d4"),
        )

    assert "internal database detail" not in str(captured_error.value)
    session.rollback.assert_called_once_with()


@pytest.mark.integration
def test_validation_error_does_not_create_rows(postgres_engine: Engine) -> None:
    session_factory = sessionmaker(postgres_engine, expire_on_commit=False)

    with session_factory() as session:
        with pytest.raises(UrlValidationError):
            create_url_mapping(session, "ftp://example.com/not-supported")

    with session_factory() as fresh_session:
        count = fresh_session.scalar(
            select(func.count())
            .select_from(UrlMapping)
            .where(UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%"))
        )
    assert count == 0
