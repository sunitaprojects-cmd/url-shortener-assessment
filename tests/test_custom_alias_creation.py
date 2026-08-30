import os
from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.models import UrlMapping
from app.schema import create_schema
from app.url_creation import (
    CustomAliasConflictError,
    UrlPersistenceError,
    create_url_mapping,
)

TEST_CODE_PREFIX = "phase3-"
TEST_ALIASES = ("sale", "summer-sale")
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
                or_(
                    UrlMapping.short_code.like(f"{TEST_CODE_PREFIX}%"),
                    UrlMapping.short_code.in_(TEST_ALIASES),
                )
            )
        )


@pytest.mark.parametrize("request_body", [{}, {"custom_alias": None}])
def test_omitted_or_null_alias_uses_automatic_generation(
    client: TestClient,
    request_body: dict,
) -> None:
    response = client.post(
        "/api/v1/urls",
        json={"url": "https://example.com/phase3-auto", **request_body},
    )

    assert response.status_code == 201
    assert response.json()["code"].startswith("phase3-auto-")


@pytest.mark.integration
def test_uppercase_alias_is_normalized_returned_and_persisted(
    client: TestClient,
    postgres_engine: Engine,
) -> None:
    response = client.post(
        "/api/v1/urls",
        json={
            "url": "https://example.com/custom",
            "custom_alias": "Summer-Sale",
        },
    )

    assert response.status_code == 201
    assert response.json()["code"] == "summer-sale"
    assert response.json()["short_url"] == f"{PUBLIC_BASE_URL}/summer-sale"
    with Session(postgres_engine) as session:
        persisted = session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == "summer-sale")
        )
    assert persisted is not None
    assert persisted.original_url == "https://example.com/custom"


@pytest.mark.parametrize(
    ("alias", "error_code"),
    [
        ("ab", "custom_alias_invalid_length"),
        ("bad/alias", "custom_alias_invalid_characters"),
        ("https://example.com/summer-sale", "custom_alias_invalid_characters"),
        ("health", "custom_alias_reserved"),
    ],
)
def test_invalid_alias_fails_before_persistence(
    client: TestClient,
    postgres_engine: Engine,
    alias: str,
    error_code: str,
) -> None:
    with postgres_engine.connect() as connection:
        count_before = connection.scalar(select(func.count()).select_from(UrlMapping))

    response = client.post(
        "/api/v1/urls",
        json={"url": "https://example.com/invalid", "custom_alias": alias},
    )

    with postgres_engine.connect() as connection:
        count_after = connection.scalar(select(func.count()).select_from(UrlMapping))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == error_code
    assert count_after == count_before


@pytest.mark.integration
def test_case_normalized_duplicate_alias_returns_409(client: TestClient) -> None:
    first_response = client.post(
        "/api/v1/urls",
        json={"url": "https://example.com/first", "custom_alias": "Sale"},
    )
    second_response = client.post(
        "/api/v1/urls",
        json={"url": "https://example.com/second", "custom_alias": "sale"},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == {
        "code": "custom_alias_conflict",
        "message": "Custom alias is already in use.",
    }


@pytest.mark.integration
def test_conflict_with_generated_code_does_not_retry(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(postgres_engine, expire_on_commit=False)
    existing_code = "phase3-generated-abcdefgh"
    with session_factory() as session:
        create_url_mapping(
            session,
            "https://example.com/generated",
            code_generator=lambda original_url: existing_code,
        )

    generator = Mock(side_effect=AssertionError("generator must not be called"))
    with session_factory() as session:
        with pytest.raises(CustomAliasConflictError):
            create_url_mapping(
                session,
                "https://example.com/custom",
                custom_alias=existing_code,
                code_generator=generator,
            )

    generator.assert_not_called()


def test_unrelated_persistence_failure_returns_sanitized_503(
    client: TestClient,
) -> None:
    with patch(
        "app.api.create_url_mapping",
        side_effect=UrlPersistenceError("internal database detail"),
    ):
        response = client.post(
            "/api/v1/urls",
            json={
                "url": "https://example.com/failure",
                "custom_alias": "phase3-failure",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "persistence_unavailable"
    assert "internal database detail" not in response.text


def test_openapi_explains_url_and_custom_alias_inputs(client: TestClient) -> None:
    request_properties = client.get("/openapi.json").json()["components"]["schemas"][
        "CreateUrlRequest"
    ]["properties"]

    assert request_properties["url"]["examples"] == [
        "https://example.com/products/item"
    ]
    assert "complete HTTP or HTTPS URL" in request_properties["url"]["description"]
    assert request_properties["custom_alias"]["examples"] == ["summer-sale"]
    assert "alias/code portion" in request_properties["custom_alias"]["description"]
    assert "PUBLIC_BASE_URL" in request_properties["custom_alias"]["description"]
