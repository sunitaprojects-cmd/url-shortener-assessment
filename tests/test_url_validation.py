import pytest

from app.url_validation import (
    MAX_URL_LENGTH,
    UrlValidationError,
    validate_and_normalize_url,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "HTTPS://EXAMPLE.COM/Guides/Start",
            "https://example.com/Guides/Start",
        ),
        ("HTTP://Example.COM", "http://example.com"),
        (
            "https://EXAMPLE.com/A//b/../c?b=2&a=1&a=3#Section-1",
            "https://example.com/A//b/../c?b=2&a=1&a=3#Section-1",
        ),
        (
            "https://example.com/a%2Fb?q=x%2By#f%20g",
            "https://example.com/a%2Fb?q=x%2By#f%20g",
        ),
    ],
)
def test_valid_urls_are_minimally_normalized(value: str, expected: str) -> None:
    assert validate_and_normalize_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not a url",
        "/relative/path",
        "ftp://example.com/file",
        "https:///missing-host",
        "https://user@example.com/path",
        "https://user:password@example.com/path",
        "https://example.com:not-a-port/path",
        "https://example.com/path with space",
        "https://example.com/path\twith-tab",
        "https://example.com/path\nwith-newline",
        "https://example.com/path\x00with-control",
        "https://example.com/path\x7fwith-delete",
    ],
)
def test_invalid_urls_are_rejected(value: str | None) -> None:
    with pytest.raises(UrlValidationError):
        validate_and_normalize_url(value)  # type: ignore[arg-type]


def test_url_at_maximum_length_is_accepted() -> None:
    prefix = "https://example.com/"
    value = prefix + ("a" * (MAX_URL_LENGTH - len(prefix)))

    assert validate_and_normalize_url(value) == value


def test_url_over_maximum_length_is_rejected() -> None:
    prefix = "https://example.com/"
    value = prefix + ("a" * (MAX_URL_LENGTH - len(prefix) + 1))

    with pytest.raises(UrlValidationError, match="4096"):
        validate_and_normalize_url(value)
