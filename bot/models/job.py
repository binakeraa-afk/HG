"""Modèle Job : une demande de récupération (un profil, un périmètre)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base
from bot.models.enums import JobStatus, MediaScope

if TYPE_CHECKING:
    from bot.models.profile import Profile


class Job(Base):
    """Unité de travail persistée — clé de la reprise après redémarrage.

    À chaque transition d'état, on met à jour la ligne. Au démarrage, on requeue
    tous les jobs non terminaux (PENDING/RESOLVING/DOWNLOADING/SENDING).
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))

    # Qui a demandé, et où renvoyer la progression.
    requested_by: Mapped[int] = mapped_column(BigInteger)
    origin_chat_id: Mapped[int] = mapped_column(BigInteger)
    progress_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    scope: Mapped[MediaScope] = mapped_column(
        Enum(MediaScope, native_enum=False, length=16), default=MediaScope.VIDEOS
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=16),
        default=JobStatus.PENDING,
        index=True,
    )
    limit: Mapped[int] = mapped_column(Integer, default=50)

    # Compteurs de progression (pour l'affichage et la reprise).
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    downloaded_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Dernière erreur technique (jamais montrée à l'utilisateur, debug only).
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Dossier de travail dédié au job (nettoyé à la fin).
    work_subdir: Mapped[str | None] = mapped_column(String(255), nullable=True)

    profile: Mapped["Profile"] = relationship("Profile", lazy="selectin")
