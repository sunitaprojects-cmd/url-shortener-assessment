import os
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import get_session
from app.main import app
from app.models import UrlMapping
from app.schema import create_schema
from app.url_resolution import UrlLookupError

TEST_CODE_PREFIX = "task7-"


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL API tests")

    engine = create_engine(database_url)
    create_schema(engine)
    _delete_test_mappings(engine)

    try:
        yield engine
    finally:
        _delete_test_mappings(engine)
        engine.dispose()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, postgres_engine: Engine):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sho.rt")

    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def _delete_test_mappings(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.delete().where(
                UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%")
            )
        )


def _failing_session(failure_point: str) -> Mock:
    session = Mock(spec=Session)
    if failure_point == "update":
        session.scalar.side_effect = SQLAlchemyError("update failed")
    else:
        session.scalar.return_value = UrlMapping(
            short_code="task7-db-failure-A1b2C3d4",
            original_url="https://example.com/failure",
        )
        session.commit.side_effect = SQLAlchemyError("commit failed")
    return session


@pytest.mark.integration
def test_known_code_redirects_to_stored_url(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    code = "task7-known-A1b2C3d4"
    original_url = "https://example.com/A//guide?b=2&a=1#Section"
    with postgres_engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.insert().values(
                short_code=code,
                original_url=original_url,
            )
        )

    response = client.get(f"/{code}")

    assert response.status_code == 307
    assert response.headers["location"] == original_url

    with Session(postgres_engine) as session:
        persisted = session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == code)
        )

    assert persisted is not None
    assert persisted.redirect_count == 1
    assert persisted.last_accessed_at is not None
    assert persisted.last_accessed_at.tzinfo is not None


@pytest.mark.integration
def test_repeated_redirects_increment_count_and_update_timestamp(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    code = "task7-repeated-A1b2C3d4"
    original_url = "https://example.com/repeated"
    with postgres_engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.insert().values(
                short_code=code,
                original_url=original_url,
            )
        )

    first_response = client.get(f"/{code}")
    with postgres_engine.begin() as connection:
        first_accessed_at = connection.scalar(
            select(UrlMapping.last_accessed_at).where(UrlMapping.short_code == code)
        )
        comparison_timestamp = datetime(2000, 1, 1, tzinfo=UTC)
        connection.execute(
            update(UrlMapping)
            .where(UrlMapping.short_code == code)
            .values(last_accessed_at=comparison_timestamp)
        )

    second_response = client.get(f"/{code}")
    with Session(postgres_engine) as session:
        persisted = session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == code)
        )

    assert first_response.status_code == 307
    assert first_accessed_at is not None
    assert second_response.status_code == 307
    assert persisted is not None
    assert persisted.redirect_count == 2
    assert persisted.last_accessed_at is not None
    assert persisted.last_accessed_at > comparison_timestamp


@pytest.mark.parametrize("code", ["task7-unknown-Z9y8X7w6", "not_valid"])
def test_unknown_or_invalid_code_returns_404_without_mutation(
    client: TestClient,
    postgres_engine: Engine,
    code: str,
) -> None:
    with postgres_engine.connect() as connection:
        count_before = connection.scalar(
            select(func.count())
            .select_from(UrlMapping)
            .where(UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%"))
        )

    response = client.get(f"/{code}")

    with postgres_engine.connect() as connection:
        count_after = connection.scalar(
            select(func.count())
            .select_from(UrlMapping)
            .where(UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%"))
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "short_url_not_found"
    assert count_after == count_before


def test_database_failure_returns_sanitized_503(client: TestClient) -> None:
    with patch(
        "app.api.resolve_url_mapping",
        side_effect=UrlLookupError("internal database detail"),
    ):
        response = client.get("/task7-failure-A1b2C3d4")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "lookup_unavailable",
        "message": "The short URL could not be resolved.",
    }
    assert "internal database detail" not in response.text


@pytest.mark.parametrize("failure_point", ["update", "commit"])
def test_update_or_commit_failure_returns_503_not_redirect(
    client: TestClient,
    failure_point: str,
) -> None:
    session = _failing_session(failure_point)

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = client.get("/task7-db-failure-A1b2C3d4")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "location" not in response.headers
    assert response.json()["detail"]["code"] == "lookup_unavailable"
    session.rollback.assert_called_once_with()


def test_reserved_application_routes_are_not_captured(client: TestClient) -> None:
    health_response = client.get("/health")
    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")
    openapi_response = client.get("/openapi.json")
    api_response = client.get("/api/v1/urls")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert docs_response.status_code == 200
    assert redoc_response.status_code == 200
    assert openapi_response.status_code == 200
    assert api_response.status_code == 405


@pytest.mark.integration
def test_create_then_redirect_end_to_end(client: TestClient) -> None:
    original_url = "https://example.com/task7-e2e?source=test#Result"

    creation_response = client.post("/api/v1/urls", json={"url": original_url})
    assert creation_response.status_code == 201
    code = creation_response.json()["code"]

    redirect_response = client.get(f"/{code}")

    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == original_url
