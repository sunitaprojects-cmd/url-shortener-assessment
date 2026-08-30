import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import UrlMapping
from app.schema import create_schema
from app.url_analytics import AnalyticsLookupError

TEST_CODE_PREFIX = "analytics-api-"


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


@pytest.mark.integration
def test_create_analytics_zero_then_redirect_updates_analytics(
    client: TestClient,
) -> None:
    original_url = "https://example.com/analytics-api-guide"
    creation_response = client.post("/api/v1/urls", json={"url": original_url})
    assert creation_response.status_code == 201
    code = creation_response.json()["code"]

    initial_response = client.get(f"/api/v1/urls/{code}/analytics")
    assert initial_response.status_code == 200
    initial = initial_response.json()
    assert initial == {
        "code": code,
        "original_url": original_url,
        "redirect_count": 0,
        "last_accessed_at": None,
        "created_at": creation_response.json()["created_at"],
    }

    first_redirect = client.get(f"/{code}")
    first_analytics = client.get(f"/api/v1/urls/{code}/analytics").json()
    second_redirect = client.get(f"/{code}")
    second_analytics = client.get(f"/api/v1/urls/{code}/analytics").json()

    assert first_redirect.status_code == 307
    assert first_analytics["redirect_count"] == 1
    assert first_analytics["last_accessed_at"] is not None
    assert second_redirect.status_code == 307
    assert second_analytics["redirect_count"] == 2
    assert second_analytics["last_accessed_at"] is not None


@pytest.mark.integration
def test_analytics_reads_do_not_mutate_mapping(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    code = "analytics-api-readonly-A1b2C3d4"
    with postgres_engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.insert().values(
                short_code=code,
                original_url="https://example.com/read-only",
            )
        )

    redirect_response = client.get(f"/{code}")
    first_read = client.get(f"/api/v1/urls/{code}/analytics").json()
    second_read = client.get(f"/api/v1/urls/{code}/analytics").json()
    with Session(postgres_engine) as session:
        persisted = session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == code)
        )

    assert redirect_response.status_code == 307
    assert first_read["redirect_count"] == second_read["redirect_count"] == 1
    assert first_read["last_accessed_at"] == second_read["last_accessed_at"]
    assert persisted is not None
    assert persisted.redirect_count == 1
    assert persisted.last_accessed_at.isoformat() == first_read["last_accessed_at"]


@pytest.mark.parametrize("code", ["analytics-api-unknown-A1b2C3d4", "not_valid"])
def test_unknown_or_invalid_code_returns_404(client: TestClient, code: str) -> None:
    response = client.get(f"/api/v1/urls/{code}/analytics")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "short_url_not_found",
        "message": "Short URL was not found.",
    }


def test_database_failure_returns_sanitized_503(client: TestClient) -> None:
    with patch(
        "app.api.get_url_analytics",
        side_effect=AnalyticsLookupError("internal database detail"),
    ):
        response = client.get("/api/v1/urls/analytics-api-failure-A1b2C3d4/analytics")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "analytics_unavailable",
        "message": "URL analytics could not be retrieved.",
    }
    assert "internal database detail" not in response.text
