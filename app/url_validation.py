from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from pydantic import AnyUrl, TypeAdapter, UrlConstraints, ValidationError

MAX_URL_LENGTH = 4096

HttpDestination = Annotated[
    AnyUrl,
    UrlConstraints(
        max_length=MAX_URL_LENGTH,
        allowed_schemes=["http", "https"],
        host_required=True,
    ),
]
_URL_ADAPTER = TypeAdapter(HttpDestination)


class UrlValidationError(ValueError):
    """Raised when a URL cannot be accepted as a redirect destination."""


def validate_and_normalize_url(value: str) -> str:
    """Validate an HTTP(S) destination and apply minimal normalization."""
    if not isinstance(value, str) or not value:
        raise UrlValidationError("URL is required.")
    if len(value) > MAX_URL_LENGTH:
        raise UrlValidationError(f"URL must not exceed {MAX_URL_LENGTH} characters.")
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise UrlValidationError(
            "URL must not contain whitespace or control characters."
        )

    try:
        parsed_url = _URL_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise UrlValidationError(
            "URL must be a valid absolute HTTP or HTTPS URL."
        ) from exc

    parsed_input = urlsplit(value)
    if not parsed_input.scheme or not parsed_input.netloc or not parsed_input.hostname:
        raise UrlValidationError("URL must include a valid hostname.")
    if parsed_url.username is not None or parsed_url.password is not None:
        raise UrlValidationError("URL must not contain credentials.")
    try:
        parsed_input.port
    except ValueError as exc:
        raise UrlValidationError("URL contains an invalid port.") from exc

    return urlunsplit(
        (
            parsed_input.scheme.lower(),
            parsed_input.netloc.lower(),
            parsed_input.path,
            parsed_input.query,
            parsed_input.fragment,
        )
    )
