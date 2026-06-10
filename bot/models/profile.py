"""Modèle Profile : un profil X suivi par le bot + son topic associé."""
from __future__ import annotations

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class Profile(Base):
    """Profil X et le topic Telegram qui lui est dédié.

    On mémorise le topic créé pour ne pas en recréer un à chaque demande sur le
    même profil (idempotence) et pour router correctement les médias.
    """

    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("username", name="uq_profiles_username"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Handle X normalisé (sans @), insensible à la casse en pratique.
    username: Mapped[str] = mapped_column(String(64), index=True)
    # Id du topic (message_thread_id) dans le supergroupe forum, si déjà créé.
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Chat cible (mémorisé pour supporter un éventuel multi-supergroupe).
    chat_id: Mapped[int] = mapped_column(BigInteger)
