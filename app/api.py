from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.custom_alias import (
    CustomAliasInvalidCharactersError,
    CustomAliasInvalidLengthError,
    CustomAliasReservedError,
)
from app.schemas import CreateUrlRequest, CreateUrlResponse, UrlAnalyticsResponse
from app.url_analytics import AnalyticsLookupError, get_url_analytics
from app.url_creation import (
    CustomAliasConflictError,
    ShortCodeCollisionError,
    UrlPersistenceError,
    create_url_mapping,
)
from app.url_resolution import UrlLookupError, resolve_url_mapping
from app.url_validation import UrlValidationError

router = APIRouter(prefix="/api/v1")
redirect_router = APIRouter()


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()


@router.post(
    "/urls",
    response_model=CreateUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_url(
    payload: CreateUrlRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> CreateUrlResponse:
    try:
        mapping = create_url_mapping(
            session,
            payload.url,
            custom_alias=payload.custom_alias,
        )
    except UrlValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_url", "message": str(exc)},
        ) from None
    except CustomAliasInvalidLengthError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "custom_alias_invalid_length", "message": str(exc)},
        ) from None
    except CustomAliasInvalidCharactersError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "custom_alias_invalid_characters",
                "message": str(exc),
            },
        ) from None
    except CustomAliasReservedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "custom_alias_reserved", "message": str(exc)},
        ) from None
    except CustomAliasConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "custom_alias_conflict",
                "message": "Custom alias is already in use.",
            },
        ) from None
    except ShortCodeCollisionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "short_code_unavailable",
                "message": "A unique short URL could not be allocated.",
            },
        ) from None
    except UrlPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "persistence_unavailable",
                "message": "The URL mapping could not be saved.",
            },
        ) from None

    return CreateUrlResponse(
        code=mapping.short_code,
        short_url=f"{request.app.state.settings.public_base_url}/{mapping.short_code}",
        original_url=mapping.original_url,
        created_at=mapping.created_at,
    )


@router.get("/urls/{code}/analytics", response_model=UrlAnalyticsResponse)
def read_url_analytics(
    code: str,
    session: Session = Depends(get_session),
) -> UrlAnalyticsResponse:
    try:
        mapping = get_url_analytics(session, code)
    except AnalyticsLookupError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "analytics_unavailable",
                "message": "URL analytics could not be retrieved.",
            },
        ) from None

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "short_url_not_found",
                "message": "Short URL was not found.",
            },
        )

    return UrlAnalyticsResponse(
        code=mapping.short_code,
        original_url=mapping.original_url,
        redirect_count=mapping.redirect_count,
        last_accessed_at=mapping.last_accessed_at,
        created_at=mapping.created_at,
    )


@redirect_router.get("/{code}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def redirect_to_original_url(
    code: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        mapping = resolve_url_mapping(session, code)
    except UrlLookupError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "lookup_unavailable",
                "message": "The short URL could not be resolved.",
            },
        ) from None

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "short_url_not_found",
                "message": "Short URL was not found.",
            },
        )

    return RedirectResponse(
        url=mapping.original_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
