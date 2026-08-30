import os
from dataclasses import dataclass

from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    public_base_url: str

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = database_url_from_environment()
        public_base_url = _required_environment_variable("PUBLIC_BASE_URL")

        normalized_public_base_url = _validate_public_base_url(public_base_url)

        return cls(
            database_url=database_url,
            public_base_url=normalized_public_base_url,
        )


def database_url_from_environment() -> str:
    database_url = _required_environment_variable("DATABASE_URL")
    _validate_database_url(database_url)
    return database_url


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigurationError(
            f"Required environment variable {name} is not configured."
        )
    return value.strip()


def _validate_database_url(value: str) -> None:
    try:
        parsed_url = make_url(value)
    except ArgumentError as exc:
        raise ConfigurationError("DATABASE_URL is not a valid database URL.") from exc

    if parsed_url.get_backend_name() != "postgresql" or not parsed_url.database:
        raise ConfigurationError("DATABASE_URL must identify a PostgreSQL database.")


def _validate_public_base_url(value: str) -> str:
    try:
        parsed_url = TypeAdapter(HttpUrl).validate_python(value)
    except ValidationError as exc:
        raise ConfigurationError(
            "PUBLIC_BASE_URL must be a valid HTTP or HTTPS URL."
        ) from exc

    if parsed_url.username or parsed_url.password:
        raise ConfigurationError("PUBLIC_BASE_URL must not contain credentials.")
    if parsed_url.path not in (None, "/") or parsed_url.query or parsed_url.fragment:
        raise ConfigurationError(
            "PUBLIC_BASE_URL must not contain a path, query, or fragment."
        )

    return str(parsed_url).rstrip("/")
