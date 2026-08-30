import pytest
from fastapi.testclient import TestClient

from app.config import ConfigurationError
from app.main import app


def test_health_check_with_valid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secret@localhost/url_shortener",
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_startup_fails_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        with TestClient(app):
            pass
