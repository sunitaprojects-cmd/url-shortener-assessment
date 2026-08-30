from datetime import datetime

from pydantic import BaseModel, Field


class CreateUrlRequest(BaseModel):
    url: str = Field(
        description=(
            "Original/destination URL to shorten. Enter the complete HTTP or HTTPS URL."
        ),
        examples=["https://example.com/products/item"],
    )
    custom_alias: str | None = Field(
        default=None,
        description=(
            "Optional custom alias. Enter only the alias/code portion, not a "
            "complete URL. Letters are case-insensitive and normalized to "
            "lowercase. The application constructs the complete short URL using "
            "PUBLIC_BASE_URL."
        ),
        examples=["summer-sale"],
    )


class CreateUrlResponse(BaseModel):
    code: str
    short_url: str
    original_url: str
    created_at: datetime


class UrlAnalyticsResponse(BaseModel):
    code: str
    original_url: str
    redirect_count: int
    last_accessed_at: datetime | None
    created_at: datetime
