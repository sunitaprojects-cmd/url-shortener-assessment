import pytest

from app.config import ConfigurationError, Settings, database_url_from_environment


VALID_DATABASE_URL = "postgresql+psycopg://app:secret@localhost/url_shortener"
VALID_PUBLIC_BASE_URL = "http://localhost:8000"


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DATABASE_URL)
    monkeypatch.setenv("PUBLIC_BASE_URL", f"{VALID_PUBLIC_BASE_URL}/")

    settings = Settings.from_environment()

    assert settings.database_url == VALID_DATABASE_URL
    assert settings.public_base_url == VALID_PUBLIC_BASE_URL


def test_database_url_loads_without_public_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DATABASE_URL)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    assert database_url_from_environment() == VALID_DATABASE_URL


@pytest.mark.parametrize("missing_name", ["DATABASE_URL", "PUBLIC_BASE_URL"])
def test_missing_required_setting_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, missing_name: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DATABASE_URL)
    monkeypatch.setenv("PUBLIC_BASE_URL", VALID_PUBLIC_BASE_URL)
    monkeypatch.delenv(missing_name)

    with pytest.raises(ConfigurationError, match=missing_name):
        Settings.from_environment()


@pytest.mark.parametrize(
    ("name", "value", "expected_message"),
    [
        ("DATABASE_URL", "sqlite:///local.db", "PostgreSQL"),
        ("PUBLIC_BASE_URL", "ftp://sho.rt", "HTTP or HTTPS"),
        ("PUBLIC_BASE_URL", "https://sho.rt/path", "path, query, or fragment"),
    ],
)
def test_invalid_setting_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    expected_message: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DATABASE_URL)
    monkeypatch.setenv("PUBLIC_BASE_URL", VALID_PUBLIC_BASE_URL)
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=expected_message):
        Settings.from_environment()
