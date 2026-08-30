import pytest

from app.custom_alias import (
    MAX_CUSTOM_ALIAS_LENGTH,
    MIN_CUSTOM_ALIAS_LENGTH,
    CustomAliasInvalidCharactersError,
    CustomAliasInvalidLengthError,
    CustomAliasReservedError,
    normalize_custom_alias,
)


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("summer-sale", "summer-sale"),
        ("summer--sale", "summer--sale"),
        ("Summer-Sale", "summer-sale"),
        ("ABC", "abc"),
        ("a1b", "a1b"),
        ("a" * MAX_CUSTOM_ALIAS_LENGTH, "a" * MAX_CUSTOM_ALIAS_LENGTH),
    ],
)
def test_valid_alias_is_normalized(alias: str, expected: str) -> None:
    assert normalize_custom_alias(alias) == expected


@pytest.mark.parametrize(
    "alias",
    [
        "ab",
        "a" * (MAX_CUSTOM_ALIAS_LENGTH + 1),
        "",
    ],
)
def test_invalid_alias_length_is_rejected(alias: str) -> None:
    with pytest.raises(CustomAliasInvalidLengthError, match="between 3 and 32"):
        normalize_custom_alias(alias)


@pytest.mark.parametrize(
    "alias",
    [
        "-summer",
        "summer-",
        "---",
        "summer sale",
        "summer/sale",
        "summer\\sale",
        "../summer",
        "summer..sale",
        "summer?sale",
        "summer#sale",
        "summer%2Fsale",
        "summer%2Esale",
        "summer\tsale",
        "summer\nsale",
        "summer\x00sale",
        "summer_sale",
        "sümmer-sale",
        "夏-sale",
    ],
)
def test_unsafe_or_unsupported_alias_is_rejected(alias: str) -> None:
    with pytest.raises(
        CustomAliasInvalidCharactersError,
        match="letters, digits, and hyphens",
    ):
        normalize_custom_alias(alias)


@pytest.mark.parametrize(
    "alias",
    ["health", "HEALTH", "docs", "redoc", "openapi.json", "api"],
)
def test_reserved_alias_is_rejected(alias: str) -> None:
    with pytest.raises(CustomAliasReservedError, match="reserved"):
        normalize_custom_alias(alias)


def test_minimum_length_alias_is_accepted() -> None:
    assert normalize_custom_alias("a" * MIN_CUSTOM_ALIAS_LENGTH) == "aaa"
