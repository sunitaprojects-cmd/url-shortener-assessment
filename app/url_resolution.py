from sqlalchemy import func, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import UrlMapping
from app.short_code import ShortCodeError, validate_routable_code


class UrlLookupError(RuntimeError):
    """Raised when a mapping lookup cannot be completed."""


def resolve_url_mapping(session: Session, code: str) -> UrlMapping | None:
    try:
        validate_routable_code(code)
    except ShortCodeError:
        return None

    try:
        mapping = session.scalar(
            update(UrlMapping)
            .where(UrlMapping.short_code == code)
            .values(
                redirect_count=UrlMapping.redirect_count + 1,
                last_accessed_at=func.now(),
            )
            .returning(UrlMapping)
        )
        if mapping is None:
            session.rollback()
            return None
        session.commit()
        return mapping
    except SQLAlchemyError:
        session.rollback()
        raise UrlLookupError("URL mapping lookup failed.") from None
