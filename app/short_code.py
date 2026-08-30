import re
import secrets
import unicodedata
from collections.abc import Callable
from urllib.parse import unquote, urlsplit

from app.custom_alias import (
    RESERVED_ROUTE_NAMES,
    CustomAliasError,
    normalize_custom_alias,
)

BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
SUFFIX_LENGTH = 8
MAX_SLUG_LENGTH = 32
MAX_SHORT_CODE_LENGTH = 64
SHORT_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-[A-Za-z0-9]{8}$")


class ShortCodeError(ValueError):
    """Raised when a short code does not satisfy the public code contract."""


def generate_short_code(
    original_url: str,
    *,
    choice: Callable[[str], str] = secrets.choice,
) -> str:
    slug = _derive_slug(original_url)
    suffix = "".join(choice(BASE62_ALPHABET) for _ in range(SUFFIX_LENGTH))
    code = f"{slug}-{suffix}"
    validate_generated_short_code(code)
    return code


def validate_generated_short_code(code: str) -> None:
    if len(code) > MAX_SHORT_CODE_LENGTH:
        raise ShortCodeError(
            f"Short code must not exceed {MAX_SHORT_CODE_LENGTH} characters."
        )
    if code.lower() in RESERVED_ROUTE_NAMES:
        raise ShortCodeError("Short code uses a reserved route name.")
    if not SHORT_CODE_PATTERN.fullmatch(code):
        raise ShortCodeError(
            "Short code must contain a lowercase slug, a hyphen, and an "
            "8-character Base62 suffix."
        )


def validate_short_code(code: str) -> None:
    """Validate the strict generated-code contract retained from Phase 1."""
    validate_generated_short_code(code)


def validate_routable_code(code: str) -> None:
    try:
        validate_generated_short_code(code)
        return
    except ShortCodeError:
        pass

    try:
        normalized_alias = normalize_custom_alias(code)
    except CustomAliasError:
        raise ShortCodeError("Short code is not routable.") from None

    if normalized_alias != code:
        raise ShortCodeError("Short code is not in canonical form.")


def _derive_slug(original_url: str) -> str:
    parsed_url = urlsplit(original_url)
    path_segments = [segment for segment in parsed_url.path.split("/") if segment]

    if path_segments:
        path_slug = _sanitize_slug(unquote(path_segments[-1]))
        if path_slug:
            return path_slug

    hostname = parsed_url.hostname or ""
    hostname_labels = hostname.split(".")
    if hostname_labels and hostname_labels[0].lower() == "www":
        hostname_labels = hostname_labels[1:]
    if hostname_labels:
        hostname_slug = _sanitize_slug(hostname_labels[0])
        if hostname_slug:
            return hostname_slug

    return "link"


def _sanitize_slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH].rstrip("-")
