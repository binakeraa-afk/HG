"""Modèle MediaItem : un média individuel rattaché à un job/profil.

Sert à l'idempotence : on identifie un média par une clé stable (id de tweet +
index, ou hash du nom de fichier). On ne renvoie jamais deux fois un média déjà
marqué SENT, même après un redémarrage en plein milieu d'un job.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base
from bot.models.enums import MediaKind, MediaStatus


class MediaItem(Base):
    __tablename__ = "media_items"
    __table_args__ = (
        # Un même média (clé stable) n'est suivi qu'une fois par profil.
        UniqueConstraint("profile_id", "stable_key", name="uq_media_profile_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )

    # Identifiant stable et déterministe du média (ex: "<tweet_id>:<n>").
    stable_key: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[MediaKind] = mapped_column(Enum(MediaKind, native_enum=False, length=8))
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, native_enum=False, length=16),
        default=MediaStatus.PENDING,
        index=True,
    )

    # Métadonnées utiles à la vérification et au debug.
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # file_id Telegram du média envoyé (permet un renvoi instantané sans re-upload).
    tg_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
