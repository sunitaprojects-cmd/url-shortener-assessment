from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import UrlMapping
from app.short_code import ShortCodeError, validate_routable_code


class AnalyticsLookupError(RuntimeError):
    """Raised when analytics cannot be read from persistence."""


def get_url_analytics(session: Session, code: str) -> UrlMapping | None:
    try:
        validate_routable_code(code)
    except ShortCodeError:
        return None

    try:
        return session.scalar(select(UrlMapping).where(UrlMapping.short_code == code))
    except SQLAlchemyError:
        raise AnalyticsLookupError("URL analytics lookup failed.") from None
