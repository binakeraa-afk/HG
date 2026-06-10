"""Regroupe les modèles pour qu'Alembic et l'ORM les découvrent tous."""
from bot.models.base import Base
from bot.models.enums import (
    JobStatus,
    MediaKind,
    MediaScope,
    MediaStatus,
)
from bot.models.job import Job
from bot.models.media import MediaItem
from bot.models.profile import Profile

__all__ = [
    "Base",
    "Job",
    "MediaItem",
    "Profile",
    "JobStatus",
    "MediaKind",
    "MediaScope",
    "MediaStatus",
]
