"""
Gestion des topics (forum) du supergroupe cible.

Pour chaque profil X, on crée (ou réutilise) un topic dédié. La création est
idempotente : on mémorise le topic_id en base. Si le topic a été supprimé côté
Telegram, on en recrée un automatiquement à la première erreur d'envoi.
"""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from bot.config import get_settings
from bot.db import repository as repo
from bot.utils.logging_config import get_logger
from bot.utils.retry import RetryExhausted, async_retry

log = get_logger("topic_manager")

# Petite palette d'icônes de topic pour varier l'affichage (ids d'emojis Telegram).
_TOPIC_ICON_COLORS = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]


class TopicManager:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()

    @async_retry(retry_on=(TelegramRetryAfter,), op_name="create_forum_topic")
    async def _create_topic(self, chat_id: int, name: str) -> int:
        """Crée un topic forum et renvoie son message_thread_id."""
        color = _TOPIC_ICON_COLORS[hash(name) % len(_TOPIC_ICON_COLORS)]
        topic = await self.bot.create_forum_topic(
            chat_id=chat_id, name=name[:128], icon_color=color
        )
        return topic.message_thread_id

    async def ensure_topic(self, profile_id: int, username: str) -> int | None:
        """Garantit l'existence d'un topic pour le profil ; renvoie son id ou None.

        - Réutilise le topic mémorisé si présent.
        - Sinon en crée un nouveau et le persiste.
        - En cas d'échec total (après retries) renvoie None : l'appelant repliera
          sur un envoi sans topic plutôt que d'échouer bruyamment.
        """
        # Réutilisation si déjà connu.
        from bot.db.engine import session_scope
        from bot.models import Profile
        from sqlalchemy import select

        async with session_scope() as s:
            res = await s.execute(select(Profile).where(Profile.id == profile_id))
            profile = res.scalar_one_or_none()
            if profile and profile.topic_id:
                return profile.topic_id

        name = f"📥 @{username}"
        try:
            topic_id = await self._create_topic(self.settings.target_chat_id, name)
        except RetryExhausted as exc:
            log.error("topic.create_failed", username=username, error=repr(exc.last_exc))
            return None
        except Exception as exc:  # noqa: BLE001
            log.error("topic.create_unexpected", username=username, error=repr(exc))
            return None

        await repo.set_profile_topic(profile_id, topic_id)
        log.info("topic.created", username=username, topic_id=topic_id)
        return topic_id

    async def reset_topic(self, profile_id: int) -> None:
        """Oublie le topic mémorisé (forcera une recréation au prochain envoi)."""
        await repo.set_profile_topic(profile_id, None)
