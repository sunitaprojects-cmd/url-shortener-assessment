from collections.abc import Callable

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.custom_alias import normalize_custom_alias
from app.models import UrlMapping
from app.short_code import generate_short_code
from app.url_validation import validate_and_normalize_url

MAX_CREATION_ATTEMPTS = 5
SHORT_CODE_CONSTRAINT = "uq_url_mappings_short_code"


class UrlCreationError(RuntimeError):
    """Base error for failures in the URL creation workflow."""


class ShortCodeCollisionError(UrlCreationError):
    """Raised when no unique short code can be committed within the retry limit."""


class UrlPersistenceError(UrlCreationError):
    """Raised when a mapping cannot be persisted for a non-collision reason."""


class CustomAliasConflictError(UrlCreationError):
    """Raised when a requested custom alias is already in use."""


def create_url_mapping(
    session: Session,
    original_url: str,
    *,
    custom_alias: str | None = None,
    code_generator: Callable[[str], str] = generate_short_code,
) -> UrlMapping:
    normalized_url = validate_and_normalize_url(original_url)

    if custom_alias is not None:
        return _create_custom_alias_mapping(
            session,
            normalized_url,
            normalize_custom_alias(custom_alias),
        )

    for _ in range(MAX_CREATION_ATTEMPTS):
        mapping = UrlMapping(
            short_code=code_generator(normalized_url),
            original_url=normalized_url,
        )
        session.add(mapping)

        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if _is_short_code_collision(exc):
                continue
            raise UrlPersistenceError("URL mapping could not be persisted.") from None
        except SQLAlchemyError:
            session.rollback()
            raise UrlPersistenceError("URL mapping could not be persisted.") from None

        return mapping

    raise ShortCodeCollisionError(
        f"Could not allocate a unique short code after {MAX_CREATION_ATTEMPTS} attempts."
    )


def _create_custom_alias_mapping(
    session: Session,
    normalized_url: str,
    custom_alias: str,
) -> UrlMapping:
    mapping = UrlMapping(short_code=custom_alias, original_url=normalized_url)
    session.add(mapping)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if _is_short_code_collision(exc):
            raise CustomAliasConflictError("Custom alias is already in use.") from None
        raise UrlPersistenceError("URL mapping could not be persisted.") from None
    except SQLAlchemyError:
        session.rollback()
        raise UrlPersistenceError("URL mapping could not be persisted.") from None

    return mapping


def _is_short_code_collision(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == SHORT_CODE_CONSTRAINT
