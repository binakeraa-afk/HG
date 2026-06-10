"""
Middleware anti-spam (throttling) par utilisateur.

Empêche un même utilisateur de déclencher une avalanche de jobs en martelant le
bot. On limite la fréquence des messages déclencheurs par user_id via une fenêtre
glissante simple. Les messages trop rapprochés sont ignorés silencieusement.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.utils.logging_config import get_logger

log = get_logger("throttling")


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.5) -> None:
        self.rate_limit = rate_limit
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            now = time.monotonic()
            last = self._last_seen.get(user.id, 0.0)
            if now - last < self.rate_limit:
                # Trop rapide : on ignore proprement sans répondre.
                log.debug("throttle.dropped", user_id=user.id)
                return None
            self._last_seen[user.id] = now
        return await handler(event, data)
