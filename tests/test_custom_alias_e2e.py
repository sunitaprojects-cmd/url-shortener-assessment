import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.main import app
from app.models import UrlMapping
from app.schema import create_schema
from app.url_creation import create_url_mapping

TEST_CODE_PREFIX = "phase3-"
PUBLIC_BASE_URL = "https://sho.rt"


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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, postgres_engine: Engine):
    monkeypatch.setenv("PUBLIC_BASE_URL", PUBLIC_BASE_URL)

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
def test_custom_alias_create_redirect_and_analytics_end_to_end(
    client: TestClient,
) -> None:
    original_url = "https://example.com/custom-alias-flow?source=test#Result"

    creation_response = client.post(
        "/api/v1/urls",
        json={"url": original_url, "custom_alias": "Phase3-E2E"},
    )

    assert creation_response.status_code == 201
    assert creation_response.json()["code"] == "phase3-e2e"
    assert creation_response.json()["short_url"] == f"{PUBLIC_BASE_URL}/phase3-e2e"

    initial_analytics = client.get("/api/v1/urls/phase3-e2e/analytics")
    assert initial_analytics.status_code == 200
    assert initial_analytics.json()["redirect_count"] == 0
    assert initial_analytics.json()["last_accessed_at"] is None

    first_redirect = client.get("/phase3-e2e")
    assert first_redirect.status_code == 307
    assert first_redirect.headers["location"] == original_url

    first_analytics = client.get("/api/v1/urls/phase3-e2e/analytics").json()
    repeated_read = client.get("/api/v1/urls/phase3-e2e/analytics").json()
    assert first_analytics["redirect_count"] == 1
    assert first_analytics["last_accessed_at"] is not None
    assert repeated_read["redirect_count"] == first_analytics["redirect_count"]
    assert repeated_read["last_accessed_at"] == first_analytics["last_accessed_at"]

    second_redirect = client.get("/phase3-e2e")
    final_analytics = client.get("/api/v1/urls/phase3-e2e/analytics")
    assert second_redirect.status_code == 307
    assert final_analytics.status_code == 200
    assert final_analytics.json()["redirect_count"] == 2
    assert final_analytics.json()["last_accessed_at"] is not None


@pytest.mark.integration
def test_mixed_case_generated_code_create_redirect_and_analytics(
    client: TestClient,
) -> None:
    original_url = "https://example.com/phase3-auto"
    generated_code = "phase3-auto-A1b2C3d4"

    def create_with_deterministic_code(session, url, *, custom_alias=None):
        return create_url_mapping(
            session,
            url,
            custom_alias=custom_alias,
            code_generator=lambda normalized_url: generated_code,
        )

    with patch(
        "app.api.create_url_mapping", side_effect=create_with_deterministic_code
    ):
        creation_response = client.post("/api/v1/urls", json={"url": original_url})

    assert creation_response.status_code == 201
    assert creation_response.json()["code"] == generated_code

    redirect_response = client.get(f"/{generated_code}")
    analytics_response = client.get(f"/api/v1/urls/{generated_code}/analytics")

    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == original_url
    assert analytics_response.status_code == 200
    assert analytics_response.json()["code"] == generated_code
    assert analytics_response.json()["redirect_count"] == 1
    assert analytics_response.json()["last_accessed_at"] is not None
