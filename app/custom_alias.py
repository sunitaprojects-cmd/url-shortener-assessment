import re

MIN_CUSTOM_ALIAS_LENGTH = 3
MAX_CUSTOM_ALIAS_LENGTH = 32
CUSTOM_ALIAS_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
RESERVED_ROUTE_NAMES = frozenset({"health", "docs", "redoc", "openapi.json", "api"})


class CustomAliasError(ValueError):
    """Base error for rejected custom aliases."""


class CustomAliasInvalidLengthError(CustomAliasError):
    """Raised when a custom alias is outside the supported length."""


class CustomAliasInvalidCharactersError(CustomAliasError):
    """Raised when a custom alias violates the allowed character pattern."""


class CustomAliasReservedError(CustomAliasError):
    """Raised when a custom alias conflicts with an application route."""


def normalize_custom_alias(alias: str) -> str:
    if not isinstance(alias, str):
        raise CustomAliasInvalidCharactersError(
            "Custom alias may contain only letters, digits, and hyphens."
        )

    normalized_alias = alias.lower()
    if normalized_alias in RESERVED_ROUTE_NAMES:
        raise CustomAliasReservedError("Custom alias is reserved.")
    if not MIN_CUSTOM_ALIAS_LENGTH <= len(normalized_alias) <= MAX_CUSTOM_ALIAS_LENGTH:
        raise CustomAliasInvalidLengthError(
            f"Custom alias must be between {MIN_CUSTOM_ALIAS_LENGTH} and "
            f"{MAX_CUSTOM_ALIAS_LENGTH} characters."
        )
    if not CUSTOM_ALIAS_PATTERN.fullmatch(normalized_alias):
        raise CustomAliasInvalidCharactersError(
            "Custom alias may contain only letters, digits, and hyphens, and must "
            "begin and end with a letter or digit."
        )

    return normalized_alias
