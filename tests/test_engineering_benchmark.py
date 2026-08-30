import os
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import get_session
from app.main import app
from app.models import UrlMapping
from app.schema import create_schema
from app.short_code import (
    SHORT_CODE_PATTERN,
    ShortCodeError,
    validate_generated_short_code,
)
from app.url_creation import (
    CustomAliasConflictError,
    UrlPersistenceError,
    create_url_mapping,
)
from app.url_analytics import AnalyticsLookupError
from app.url_resolution import UrlLookupError

PUBLIC_BASE_URL = "http://localhost:8000"
NON_PREFIXED_BENCHMARK_ALIASES = ("b3x", "b" * 32, "1bench9")


@dataclass(frozen=True)
class BenchmarkCase:
    category: str
    name: str
    check: Callable[[TestClient, Engine, object], None]
    value: object = None


@pytest.fixture(scope="module")
def benchmark_engine() -> Iterator[Engine]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for the engineering benchmark")
    engine = create_engine(database_url)
    create_schema(engine)
    yield engine
    _delete_benchmark_mappings(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def benchmark_client(benchmark_engine: Engine) -> Iterator[TestClient]:
    with TestClient(app, follow_redirects=False) as client:
        yield client


@pytest.fixture(autouse=True)
def isolate_case(benchmark_engine: Engine) -> Iterator[None]:
    _delete_benchmark_mappings(benchmark_engine)
    yield
    app.dependency_overrides.clear()
    _delete_benchmark_mappings(benchmark_engine)


def _delete_benchmark_mappings(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            UrlMapping.__table__.delete().where(
                (UrlMapping.short_code.like("bench-%"))
                | (UrlMapping.short_code.in_(NON_PREFIXED_BENCHMARK_ALIASES))
            )
        )


def _create(
    client: TestClient,
    *,
    url: str = "https://example.com/bench-item",
    alias: object = ...,
):
    body = {"url": url}
    if alias is not ...:
        body["custom_alias"] = alias
    return client.post("/api/v1/urls", json=body)


def _analytics(client: TestClient, code: str):
    return client.get(f"/api/v1/urls/{code}/analytics")


def check_auto_create(client: TestClient, engine: Engine, value: object) -> None:
    response = _create(client, url=str(value or "https://example.com/bench-auto"))
    assert response.status_code == 201
    assert SHORT_CODE_PATTERN.fullmatch(response.json()["code"])


def check_custom_create(client: TestClient, engine: Engine, value: object) -> None:
    supplied, expected = value
    response = _create(client, alias=supplied)
    assert response.status_code == 201
    assert response.json()["code"] == expected
    assert response.json()["short_url"] == f"{PUBLIC_BASE_URL}/{expected}"


def check_redirect_flow(client: TestClient, engine: Engine, value: object) -> None:
    alias, redirects = value
    original = f"https://example.com/{alias}?source=bench#Result"
    created = _create(client, url=original, alias=alias)
    assert created.status_code == 201
    for _ in range(redirects):
        response = client.get(f"/{alias}")
        assert response.status_code == 307
        assert response.headers["location"] == original
    analytics = _analytics(client, alias).json()
    assert analytics["redirect_count"] == redirects
    assert (analytics["last_accessed_at"] is None) is (redirects == 0)


def check_auto_optional(client: TestClient, engine: Engine, value: object) -> None:
    response = _create(
        client,
        url="https://example.com/bench-optional",
        alias=value,
    )
    assert response.status_code == 201
    assert response.json()["code"].startswith("bench-optional-")


def check_error_status(client: TestClient, engine: Engine, value: object) -> None:
    method, path, body, status_code, error_code = value
    response = (
        getattr(client, method)(path, json=body)
        if body is not None
        else getattr(client, method)(path)
    )
    assert response.status_code == status_code
    if error_code:
        assert response.json()["detail"]["code"] == error_code


def check_duplicate_alias(client: TestClient, engine: Engine, value: object) -> None:
    first, second = value
    assert _create(client, alias=first).status_code == 201
    response = _create(client, url="https://example.com/bench-second", alias=second)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "custom_alias_conflict"


def check_alias_rejected(client: TestClient, engine: Engine, value: object) -> None:
    aliases, expected_code = value
    if isinstance(aliases, str):
        aliases = [aliases]
    for alias in aliases:
        response = _create(client, alias=alias)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == expected_code


def check_destination_rejected(
    client: TestClient, engine: Engine, value: object
) -> None:
    urls = [value] if isinstance(value, str) else value
    for url in urls:
        response = _create(client, url=url)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_url"


def check_destination_preserved(
    client: TestClient, engine: Engine, value: object
) -> None:
    original, expected = value
    response = _create(client, url=original, alias="bench-semantic")
    assert response.status_code == 201
    assert response.json()["original_url"] == expected
    redirect = client.get("/bench-semantic")
    assert redirect.status_code == 307
    assert redirect.headers["location"] == expected


def check_route(client: TestClient, engine: Engine, value: object) -> None:
    path, status_code = value
    assert client.get(path).status_code == status_code


def check_analytics_read_only(
    client: TestClient, engine: Engine, value: object
) -> None:
    alias = "bench-read-only"
    assert _create(client, alias=alias).status_code == 201
    assert client.get(f"/{alias}").status_code == 307
    first = _analytics(client, alias).json()
    second = _analytics(client, alias).json()
    assert first["redirect_count"] == second["redirect_count"] == 1
    assert first["last_accessed_at"] == second["last_accessed_at"]


def check_response_fields(client: TestClient, engine: Engine, value: object) -> None:
    created = _create(client, alias="bench-fields").json()
    assert set(created) == {"code", "short_url", "original_url", "created_at"}
    analytics = _analytics(client, "bench-fields").json()
    assert set(analytics) == {
        "code",
        "original_url",
        "redirect_count",
        "last_accessed_at",
        "created_at",
    }


def check_duplicate_destination(
    client: TestClient, engine: Engine, value: object
) -> None:
    url = "https://example.com/bench-duplicate-destination"
    first = _create(client, url=url).json()["code"]
    second = _create(client, url=url).json()["code"]
    assert first != second


def check_long_url(client: TestClient, engine: Engine, value: object) -> None:
    length, expected_status = value
    prefix = "https://example.com/"
    url = prefix + "a" * (length - len(prefix))
    assert _create(client, url=url).status_code == expected_status


def check_generated_mixed_case(
    client: TestClient, engine: Engine, value: object
) -> None:
    code = "bench-mixed-A1b2C3d4"

    def deterministic(session, url, *, custom_alias=None):
        return create_url_mapping(
            session,
            url,
            custom_alias=custom_alias,
            code_generator=lambda normalized_url: code,
        )

    with patch("app.api.create_url_mapping", side_effect=deterministic):
        created = _create(client, url="https://example.com/bench-mixed")
    assert created.status_code == 201
    assert client.get(f"/{code}").status_code == 307
    assert _analytics(client, code).json()["redirect_count"] == 1


def check_auto_collision_retry(
    client: TestClient, engine: Engine, value: object
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            UrlMapping(
                short_code="bench-collision-A1b2C3d4",
                original_url="https://example.com/existing",
            )
        )
        session.commit()
        candidates = iter(("bench-collision-A1b2C3d4", "bench-success-Z9y8X7w6"))
        mapping = create_url_mapping(
            session,
            "https://example.com/new",
            code_generator=lambda normalized_url: next(candidates),
        )
    assert mapping.short_code == "bench-success-Z9y8X7w6"


def check_custom_conflict_no_retry(
    client: TestClient, engine: Engine, value: object
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            UrlMapping(
                short_code="bench-no-retry",
                original_url="https://example.com/existing",
            )
        )
        session.commit()
        generator = Mock(side_effect=AssertionError("must not retry"))
        with pytest.raises(CustomAliasConflictError):
            create_url_mapping(
                session,
                "https://example.com/new",
                custom_alias="bench-no-retry",
                code_generator=generator,
            )
    generator.assert_not_called()


def check_create_failure(client: TestClient, engine: Engine, value: object) -> None:
    with patch(
        "app.api.create_url_mapping",
        side_effect=UrlPersistenceError("driver sql secret"),
    ):
        response = _create(client, alias="bench-create-failure")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "persistence_unavailable"
    assert "driver sql secret" not in response.text


def check_lookup_failure(client: TestClient, engine: Engine, value: object) -> None:
    with patch(
        "app.api.resolve_url_mapping",
        side_effect=UrlLookupError("driver sql secret"),
    ):
        response = client.get("/bench-lookup-A1b2C3d4")
    assert response.status_code == 503
    assert "location" not in response.headers
    assert "driver sql secret" not in response.text


def check_analytics_failure(client: TestClient, engine: Engine, value: object) -> None:
    with patch(
        "app.api.get_url_analytics",
        side_effect=AnalyticsLookupError("driver sql secret"),
    ):
        response = _analytics(client, "bench-analytics-failure")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "analytics_unavailable"
    assert "driver sql secret" not in response.text


def check_redirect_session_failure(
    client: TestClient, engine: Engine, value: object
) -> None:
    failure_point = str(value)
    session = Mock(spec=Session)
    if failure_point == "update":
        session.scalar.side_effect = SQLAlchemyError("internal")
    else:
        session.scalar.return_value = UrlMapping(
            short_code="bench-session-failure",
            original_url="https://example.com",
        )
        session.commit.side_effect = SQLAlchemyError("internal")

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    response = client.get("/bench-session-failure")
    assert response.status_code == 503
    assert "location" not in response.headers
    session.rollback.assert_called_once_with()


def check_service_rollback(client: TestClient, engine: Engine, value: object) -> None:
    session = Mock(spec=Session)
    session.commit.side_effect = SQLAlchemyError("internal")
    with pytest.raises(UrlPersistenceError):
        create_url_mapping(
            session,
            "https://example.com/bench-rollback",
            custom_alias="bench-rollback" if value == "custom" else None,
        )
    session.rollback.assert_called_once_with()


def check_committed_mapping(client: TestClient, engine: Engine, value: object) -> None:
    response = _create(client, alias="bench-committed")
    with Session(engine) as session:
        persisted = session.scalar(
            select(UrlMapping).where(UrlMapping.short_code == "bench-committed")
        )
    assert response.status_code == 201
    assert persisted is not None


def check_strict_generated(client: TestClient, engine: Engine, value: object) -> None:
    if value == "valid":
        validate_generated_short_code("bench-strict-A1b2C3d4")
    else:
        with pytest.raises(ShortCodeError):
            validate_generated_short_code(str(value))


def check_public_base_not_host(
    client: TestClient, engine: Engine, value: object
) -> None:
    response = client.post(
        "/api/v1/urls",
        headers={"host": "attacker.example"},
        json={"url": "https://example.com", "custom_alias": "bench-base"},
    )
    assert response.json()["short_url"] == f"{PUBLIC_BASE_URL}/bench-base"


def check_error_redaction(client: TestClient, engine: Engine, value: object) -> None:
    secret = str(value)
    with patch(
        "app.api.create_url_mapping",
        side_effect=UrlPersistenceError(secret),
    ):
        response = _create(client, alias="bench-redaction")
    assert response.status_code == 503
    assert secret not in response.text


def check_analytics_isolation(
    client: TestClient, engine: Engine, value: object
) -> None:
    assert _create(client, alias="bench-private-one").status_code == 201
    assert _create(client, alias="bench-private-two").status_code == 201
    assert client.get("/bench-private-one").status_code == 307
    response = _analytics(client, "bench-private-two")
    assert response.json()["code"] == "bench-private-two"
    assert response.json()["redirect_count"] == 0
    assert "bench-private-one" not in response.text


def check_no_visitor_telemetry(
    client: TestClient, engine: Engine, value: object
) -> None:
    columns = set(UrlMapping.__table__.columns.keys())
    assert columns == {
        "id",
        "short_code",
        "original_url",
        "redirect_count",
        "last_accessed_at",
        "created_at",
    }


C = BenchmarkCase
CORE = "1_core_functional_flows"
BOUNDARY = "2_boundary_and_edge_cases"
GUARDRAIL = "3_guardrails_and_security"
ROUTING = "4_routing_and_namespace"
PERSISTENCE = "5_persistence_and_failure"
REGRESSION = "6_cross_phase_regression"
SEMANTICS = "7_destination_semantics"
PRIVACY = "8_information_exposure"

CASES = [
    C(CORE, "01_auto_shortening", check_auto_create),
    C(
        CORE,
        "02_custom_creation",
        check_custom_create,
        ("bench-custom", "bench-custom"),
    ),
    C(
        CORE,
        "03_uppercase_normalization",
        check_custom_create,
        ("Bench-Upper", "bench-upper"),
    ),
    C(CORE, "04_custom_redirect", check_redirect_flow, ("bench-redirect", 1)),
    C(CORE, "05_analytics_before_redirect", check_redirect_flow, ("bench-zero", 0)),
    C(CORE, "06_analytics_after_redirect", check_redirect_flow, ("bench-one", 1)),
    C(CORE, "07_repeated_redirects", check_redirect_flow, ("bench-two", 2)),
    C(CORE, "08_analytics_read_only", check_analytics_read_only),
    C(CORE, "09_omitted_alias", check_auto_create, "https://example.com/bench-omitted"),
    C(CORE, "10_null_alias", check_auto_optional, None),
    C(
        CORE,
        "11_unknown_404",
        check_error_status,
        ("get", "/bench-unknown", None, 404, "short_url_not_found"),
    ),
    C(
        CORE,
        "12_invalid_code_404",
        check_error_status,
        ("get", "/not_valid", None, 404, "short_url_not_found"),
    ),
    C(
        CORE,
        "13_duplicate_409",
        check_duplicate_alias,
        ("bench-duplicate", "bench-duplicate"),
    ),
    C(
        CORE,
        "14_invalid_alias_422",
        check_alias_rejected,
        ("bad/alias", "custom_alias_invalid_characters"),
    ),
    C(CORE, "15_invalid_url_422", check_destination_rejected, "ftp://example.com"),
    C(CORE, "16_create_503", check_create_failure),
    C(CORE, "17_lookup_503", check_lookup_failure),
    C(CORE, "18_generated_base_url", check_public_base_not_host),
    C(
        CORE,
        "19_custom_base_url",
        check_custom_create,
        ("bench-short-url", "bench-short-url"),
    ),
    C(CORE, "20_response_fields", check_response_fields),
    C(BOUNDARY, "01_alias_minimum", check_custom_create, ("b3x", "b3x")),
    C(BOUNDARY, "02_alias_maximum", check_custom_create, ("b" * 32, "b" * 32)),
    C(
        BOUNDARY,
        "03_empty_alias",
        check_alias_rejected,
        ("", "custom_alias_invalid_length"),
    ),
    C(
        BOUNDARY,
        "04_alias_too_long",
        check_alias_rejected,
        ("b" * 33, "custom_alias_invalid_length"),
    ),
    C(BOUNDARY, "05_url_4096", check_long_url, (4096, 201)),
    C(BOUNDARY, "06_url_4097", check_long_url, (4097, 422)),
    C(BOUNDARY, "07_duplicate_destination", check_duplicate_destination),
    C(
        BOUNDARY,
        "08_query",
        check_destination_preserved,
        (
            "https://example.com/bench-query?b=2&a=1&a=3",
            "https://example.com/bench-query?b=2&a=1&a=3",
        ),
    ),
    C(
        BOUNDARY,
        "09_fragment",
        check_destination_preserved,
        (
            "https://example.com/bench-fragment#Section",
            "https://example.com/bench-fragment#Section",
        ),
    ),
    C(
        BOUNDARY,
        "10_explicit_port",
        check_destination_preserved,
        ("https://example.com:8443/bench-port", "https://example.com:8443/bench-port"),
    ),
    C(
        BOUNDARY,
        "11_unusual_path",
        check_destination_preserved,
        (
            "https://example.com/A//bench/../item",
            "https://example.com/A//bench/../item",
        ),
    ),
    C(
        BOUNDARY,
        "12_http_valid",
        check_destination_preserved,
        ("http://example.com/bench-http", "http://example.com/bench-http"),
    ),
    C(
        BOUNDARY,
        "13_hostname_fallback",
        check_auto_create,
        "https://benchhost.example/",
    ),
    C(
        BOUNDARY,
        "14_repeated_hyphen",
        check_custom_create,
        ("bench--sale", "bench--sale"),
    ),
    C(BOUNDARY, "15_digit_boundaries", check_custom_create, ("1bench9", "1bench9")),
    C(
        GUARDRAIL,
        "01_space",
        check_alias_rejected,
        ("bench sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "02_forward_slash",
        check_alias_rejected,
        ("bench/sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "03_backslash",
        check_alias_rejected,
        ("bench\\sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "04_traversal",
        check_alias_rejected,
        ("../bench", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "05_encoded_routing",
        check_alias_rejected,
        (
            ["bench%2Fsale", "bench%2Esale", "bench%3Fsale", "bench%23sale"],
            "custom_alias_invalid_characters",
        ),
    ),
    C(
        GUARDRAIL,
        "06_question",
        check_alias_rejected,
        ("bench?sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "07_hash",
        check_alias_rejected,
        ("bench#sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "08_ampersand",
        check_alias_rejected,
        ("bench&sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "09_equals",
        check_alias_rejected,
        ("bench=sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "10_tab",
        check_alias_rejected,
        ("bench\tsale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "11_crlf",
        check_alias_rejected,
        (["bench\rsale", "bench\nsale"], "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "12_null",
        check_alias_rejected,
        ("bench\x00sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "13_underscore_punctuation",
        check_alias_rejected,
        (["bench_sale", "bench!sale"], "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "14_unicode",
        check_alias_rejected,
        ("bénch-sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "15_homoglyph",
        check_alias_rejected,
        ("bеnch-sale", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "16_emoji",
        check_alias_rejected,
        ("bench-🚀", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "17_sql_style",
        check_alias_rejected,
        ("bench'--drop", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "18_script_and_api_path",
        check_alias_rejected,
        (["<script>", "api/v1/urls"], "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "19_complete_url_alias",
        check_alias_rejected,
        ("https://example.com/bench", "custom_alias_invalid_characters"),
    ),
    C(
        GUARDRAIL,
        "20_unsafe_destinations",
        check_destination_rejected,
        [
            "ftp://example.com",
            "javascript:alert(1)",
            "file:///tmp/data",
            "https://user:pass@example.com",
        ],
    ),
    C(ROUTING, "01_health", check_route, ("/health", 200)),
    C(ROUTING, "02_docs", check_route, ("/docs", 200)),
    C(ROUTING, "03_redoc", check_route, ("/redoc", 200)),
    C(ROUTING, "04_openapi", check_route, ("/openapi.json", 200)),
    C(ROUTING, "05_api_route", check_route, ("/api/v1/urls", 405)),
    C(
        ROUTING,
        "06_reserved_aliases",
        check_alias_rejected,
        (["health", "docs", "redoc", "openapi.json", "api"], "custom_alias_reserved"),
    ),
    C(
        ROUTING,
        "07_generated_namespace_conflict",
        check_duplicate_alias,
        ("bench-shared-abcdefgh", "bench-shared-abcdefgh"),
    ),
    C(ROUTING, "08_case_conflict", check_duplicate_alias, ("Bench-Case", "bench-case")),
    C(
        ROUTING,
        "09_unknown_code",
        check_error_status,
        ("get", "/bench-missing-A1b2C3d4", None, 404, "short_url_not_found"),
    ),
    C(ROUTING, "10_mixed_base62", check_generated_mixed_case),
    C(PERSISTENCE, "01_auto_collision_retry", check_auto_collision_retry),
    C(PERSISTENCE, "02_custom_no_retry", check_custom_conflict_no_retry),
    C(PERSISTENCE, "03_create_failure", check_create_failure),
    C(PERSISTENCE, "04_lookup_failure", check_lookup_failure),
    C(PERSISTENCE, "05_analytics_failure", check_analytics_failure),
    C(
        PERSISTENCE,
        "06_redirect_update_failure",
        check_redirect_session_failure,
        "update",
    ),
    C(
        PERSISTENCE,
        "07_redirect_commit_failure",
        check_redirect_session_failure,
        "commit",
    ),
    C(PERSISTENCE, "08_auto_rollback", check_service_rollback, "auto"),
    C(PERSISTENCE, "09_custom_rollback", check_service_rollback, "custom"),
    C(PERSISTENCE, "10_commit_before_response", check_committed_mapping),
    C(REGRESSION, "01_phase1_generated_format", check_strict_generated, "valid"),
    C(
        REGRESSION,
        "02_custom_does_not_weaken_generated",
        check_strict_generated,
        "summer-sale",
    ),
    C(
        REGRESSION,
        "03_phase1_url_validation",
        check_destination_rejected,
        "ftp://example.com",
    ),
    C(REGRESSION, "04_phase1_307", check_redirect_flow, ("bench-phase1", 1)),
    C(REGRESSION, "05_phase1_health", check_route, ("/health", 200)),
    C(REGRESSION, "06_phase2_generated_analytics", check_generated_mixed_case),
    C(
        REGRESSION,
        "07_phase2_custom_analytics",
        check_redirect_flow,
        ("bench-phase2", 1),
    ),
    C(REGRESSION, "08_creation_contract", check_response_fields),
    C(REGRESSION, "09_public_base", check_public_base_not_host),
    C(REGRESSION, "10_duplicate_original", check_duplicate_destination),
    C(
        SEMANTICS,
        "01_path_case",
        check_destination_preserved,
        ("https://example.com/Bench/Path", "https://example.com/Bench/Path"),
    ),
    C(
        SEMANTICS,
        "02_query_order",
        check_destination_preserved,
        (
            "https://example.com/bench?q=2&q=1&a=3",
            "https://example.com/bench?q=2&q=1&a=3",
        ),
    ),
    C(
        SEMANTICS,
        "03_fragment",
        check_destination_preserved,
        ("https://example.com/bench#ExactCase", "https://example.com/bench#ExactCase"),
    ),
    C(
        SEMANTICS,
        "04_port",
        check_destination_preserved,
        ("http://example.com:8080/bench", "http://example.com:8080/bench"),
    ),
    C(
        SEMANTICS,
        "05_encoded_path",
        check_destination_preserved,
        ("https://example.com/bench%2Fitem", "https://example.com/bench%2Fitem"),
    ),
    C(
        SEMANTICS,
        "06_encoded_query",
        check_destination_preserved,
        ("https://example.com/bench?q=x%2By", "https://example.com/bench?q=x%2By"),
    ),
    C(
        SEMANTICS,
        "07_double_slash",
        check_destination_preserved,
        ("https://example.com/A//bench", "https://example.com/A//bench"),
    ),
    C(
        SEMANTICS,
        "08_dot_segment",
        check_destination_preserved,
        ("https://example.com/A/../bench", "https://example.com/A/../bench"),
    ),
    C(
        SEMANTICS,
        "09_trailing_slash",
        check_destination_preserved,
        ("https://example.com/bench/", "https://example.com/bench/"),
    ),
    C(
        SEMANTICS,
        "10_no_http_upgrade",
        check_destination_preserved,
        ("http://example.com/bench", "http://example.com/bench"),
    ),
    C(
        PRIVACY,
        "01_no_sql_table_constraint",
        check_error_redaction,
        "SELECT * FROM url_mappings uq_url_mappings_short_code",
    ),
    C(
        PRIVACY,
        "02_no_stack_trace",
        check_error_redaction,
        "Traceback File app/api.py line 42",
    ),
    C(
        PRIVACY,
        "03_no_connection_driver",
        check_error_redaction,
        "postgresql://secret psycopg OperationalError",
    ),
    C(PRIVACY, "04_analytics_isolation", check_analytics_isolation),
    C(PRIVACY, "05_no_visitor_telemetry", check_no_visitor_telemetry),
]

EXPECTED_COUNTS = {
    CORE: 20,
    BOUNDARY: 15,
    GUARDRAIL: 20,
    ROUTING: 10,
    PERSISTENCE: 10,
    REGRESSION: 10,
    SEMANTICS: 10,
    PRIVACY: 5,
}
assert len(CASES) == 100
assert Counter(case.category for case in CASES) == EXPECTED_COUNTS


@pytest.mark.integration
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: f"{case.category}__{case.name}",
)
def test_engineering_benchmark(
    case: BenchmarkCase,
    benchmark_client: TestClient,
    benchmark_engine: Engine,
) -> None:
    case.check(benchmark_client, benchmark_engine, case.value)
