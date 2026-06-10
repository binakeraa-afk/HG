"""Déclaratif SQLAlchemy 2.0 commun à tous les modèles."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Horodatage UTC timezone-aware (évite les ambiguïtés)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base déclarative + colonnes d'audit communes."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )
