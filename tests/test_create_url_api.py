import os
from collections.abc import Iterator
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import UrlMapping
from app.schema import create_schema
from app.url_creation import ShortCodeCollisionError, UrlPersistenceError

TEST_CODE_PREFIX = "task6-"
PUBLIC_BASE_URL = "https://sho.rt"


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
    monkeypatch.setenv("PUBLIC_BASE_URL", PUBLIC_BASE_URL)

    with TestClient(app, base_url="https://untrusted-host.test") as test_client:
        yield test_client


def _delete_test_mappings(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.delete().where(
                UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%")
            )
        )


@pytest.mark.integration
def test_create_url_returns_201_and_persists_mapping(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    submitted_url = "HTTPS://EXAMPLE.COM/task6-guide?b=2&a=1#Section"

    response = client.post("/api/v1/urls", json={"url": submitted_url})

    assert response.status_code == 201
    body = response.json()
    assert body["code"].startswith(TEST_CODE_PREFIX)
    assert body["short_url"] == f"{PUBLIC_BASE_URL}/{body['code']}"
    assert "untrusted-host.test" not in body["short_url"]
    assert body["original_url"] == ("https://example.com/task6-guide?b=2&a=1#Section")
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None

    with Session(postgres_engine) as fresh_session:
        persisted = fresh_session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == body["code"])
        )

    assert persisted is not None
    assert persisted.original_url == body["original_url"]


def test_invalid_url_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/urls",
        json={"url": "ftp://example.com/not-supported"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_url"


def test_collision_exhaustion_returns_sanitized_503(client: TestClient) -> None:
    with patch(
        "app.api.create_url_mapping",
        side_effect=ShortCodeCollisionError("internal collision detail"),
    ):
        response = client.post(
            "/api/v1/urls",
            json={"url": "https://example.com/task6-collision"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "short_code_unavailable",
        "message": "A unique short URL could not be allocated.",
    }
    assert "internal collision detail" not in response.text


def test_persistence_failure_returns_sanitized_503(client: TestClient) -> None:
    with patch(
        "app.api.create_url_mapping",
        side_effect=UrlPersistenceError("internal database detail"),
    ):
        response = client.post(
            "/api/v1/urls",
            json={"url": "https://example.com/task6-failure"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "persistence_unavailable",
        "message": "The URL mapping could not be saved.",
    }
    assert "internal database detail" not in response.text
