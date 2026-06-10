"""
Rapporteur de progression utilisateur.

Affiche une barre de progression « propre » et la met à jour par édition de message.
Les éditions sont throttlées (≥ 3 s d'intervalle) pour ne pas se faire rate-limiter
par Telegram. Toutes les erreurs d'édition sont silencieuses : la progression est
un confort, jamais une source d'erreur visible.
"""
from __future__ import annotations

import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.utils.logging_config import get_logger

log = get_logger("progress")

_MIN_EDIT_INTERVAL = 3.0  # secondes entre deux éditions


def _bar(done: int, total: int, width: int = 16) -> str:
    """Construit une barre de progression textuelle."""
    if total <= 0:
        return "▱" * width
    ratio = max(0.0, min(1.0, done / total))
    filled = int(ratio * width)
    return "▰" * filled + "▱" * (width - filled)


class ProgressReporter:
    def __init__(self, bot: Bot, chat_id: int, message_id: int | None) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self._last_edit = 0.0
        self._last_text = ""

    async def update(
        self,
        *,
        username: str,
        phase: str,
        found: int,
        sent: int,
        failed: int,
        force: bool = False,
    ) -> None:
        """Met à jour le message de progression (throttlé)."""
        if self.message_id is None:
            return
        now = time.monotonic()
        if not force and (now - self._last_edit) < _MIN_EDIT_INTERVAL:
            return

        total = max(found, sent + failed)
        text = (
            f"📥 <b>@{username}</b>\n"
            f"{_bar(sent + failed, total)}\n\n"
            f"<b>Étape :</b> {phase}\n"
            f"<b>Trouvés :</b> {found}\n"
            f"<b>Envoyés :</b> {sent}\n"
            + (f"<b>Ignorés :</b> {failed}\n" if failed else "")
        )
        if text == self._last_text and not force:
            return

        try:
            await self.bot.edit_message_text(
                text=text,
                chat_id=self.chat_id,
                message_id=self.message_id,
            )
            self._last_edit = now
            self._last_text = text
        except TelegramRetryAfter as exc:
            # On respecte le délai imposé mais sans bloquer le job.
            self._last_edit = now + float(getattr(exc, "retry_after", 5))
        except TelegramBadRequest:
            # « message is not modified » ou message supprimé : on ignore.
            self._last_edit = now
        except Exception as exc:  # noqa: BLE001
            log.debug("progress.edit_failed", error=repr(exc))

    async def finalize(self, *, username: str, sent: int, failed: int) -> None:
        """Message final récapitulatif."""
        if self.message_id is None:
            return
        text = (
            f"✅ <b>@{username}</b> — terminé\n"
            f"{_bar(1, 1)}\n\n"
            f"<b>Médias envoyés :</b> {sent}\n"
            + (f"<b>Ignorés :</b> {failed}\n" if failed else "")
        )
        try:
            await self.bot.edit_message_text(
                text=text, chat_id=self.chat_id, message_id=self.message_id
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("progress.finalize_failed", error=repr(exc))
