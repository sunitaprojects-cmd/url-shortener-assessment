import re

import pytest

from app.short_code import (
    BASE62_ALPHABET,
    MAX_SHORT_CODE_LENGTH,
    RESERVED_ROUTE_NAMES,
    SHORT_CODE_PATTERN,
    ShortCodeError,
    generate_short_code,
    validate_generated_short_code,
    validate_routable_code,
    validate_short_code,
)


def fixed_choice(character: str):
    def choose(alphabet: str) -> str:
        assert alphabet == BASE62_ALPHABET
        return character

    return choose


@pytest.mark.parametrize(
    ("url", "expected_slug"),
    [
        ("https://example.com/guides/Engineering-Assessment", "engineering-assessment"),
        ("https://example.com/Some_FILE...Name", "some-file-name"),
        ("https://example.com/caf%C3%A9", "cafe"),
        ("https://www.Example.com/", "example"),
        ("https://localhost", "localhost"),
        ("https://---/!!!", "link"),
    ],
)
def test_slug_derivation(url: str, expected_slug: str) -> None:
    code = generate_short_code(url, choice=fixed_choice("A"))

    assert code == f"{expected_slug}-AAAAAAAA"


def test_long_slug_is_truncated_to_32_characters() -> None:
    code = generate_short_code(
        f"https://example.com/{'a' * 40}",
        choice=fixed_choice("0"),
    )

    slug, suffix = code.rsplit("-", 1)
    assert slug == "a" * 32
    assert suffix == "0" * 8


def test_query_and_fragment_do_not_affect_slug() -> None:
    without_extras = generate_short_code(
        "https://example.com/guide",
        choice=fixed_choice("B"),
    )
    with_extras = generate_short_code(
        "https://example.com/guide?slug=ignored#also-ignored",
        choice=fixed_choice("B"),
    )

    assert with_extras == without_extras == "guide-BBBBBBBB"


def test_suffix_is_exactly_eight_base62_characters() -> None:
    characters = iter("0Az9By8X")
    code = generate_short_code(
        "https://example.com/guide",
        choice=lambda alphabet: next(characters),
    )

    suffix = code.rsplit("-", 1)[1]
    assert suffix == "0Az9By8X"
    assert len(suffix) == 8
    assert all(character in BASE62_ALPHABET for character in suffix)


def test_deterministic_choice_is_called_for_each_suffix_character() -> None:
    calls = 0

    def choose(alphabet: str) -> str:
        nonlocal calls
        calls += 1
        return alphabet[0]

    assert generate_short_code("https://example.com/path", choice=choose) == (
        "path-00000000"
    )
    assert calls == 8


@pytest.mark.parametrize("reserved_name", sorted(RESERVED_ROUTE_NAMES))
def test_reserved_route_names_are_rejected(reserved_name: str) -> None:
    with pytest.raises(ShortCodeError, match="reserved"):
        validate_short_code(reserved_name)


def test_generated_code_has_valid_format_and_length() -> None:
    code = generate_short_code(
        f"https://example.com/{'a' * 100}",
        choice=fixed_choice("z"),
    )

    assert len(code) <= MAX_SHORT_CODE_LENGTH
    assert SHORT_CODE_PATTERN.fullmatch(code)
    assert re.fullmatch(r"[A-Za-z0-9-]+", code)


@pytest.mark.parametrize(
    "code",
    [
        "Upper-Slug-12345678",
        "bad_slug-12345678",
        "slug-short",
        "slug-1234567!",
        f"{'a' * 56}-12345678",
    ],
)
def test_invalid_complete_codes_are_rejected(code: str) -> None:
    with pytest.raises(ShortCodeError):
        validate_short_code(code)


def test_generated_code_validation_remains_strict() -> None:
    validate_generated_short_code("guide-A1b2C3d4")

    with pytest.raises(ShortCodeError):
        validate_generated_short_code("summer-sale")


@pytest.mark.parametrize(
    "code",
    [
        "guide-A1b2C3d4",
        "summer-sale",
        "summer--sale",
        "abc",
    ],
)
def test_generated_and_custom_codes_are_routable(code: str) -> None:
    validate_routable_code(code)


@pytest.mark.parametrize(
    "code",
    [
        "Summer-Sale",
        "-summer",
        "summer-",
        "health",
        "not_valid",
    ],
)
def test_noncanonical_or_invalid_alias_is_not_routable(code: str) -> None:
    with pytest.raises(ShortCodeError):
        validate_routable_code(code)
