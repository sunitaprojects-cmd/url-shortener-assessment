from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class UrlMapping(Base):
    __tablename__ = "url_mappings"
    __table_args__ = (
        UniqueConstraint("short_code", name="uq_url_mappings_short_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    short_code: Mapped[str] = mapped_column(String(64), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
