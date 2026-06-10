"""
Middleware de contrôle d'accès.

Si ADMIN_USER_IDS est renseigné, seuls ces utilisateurs peuvent piloter le bot ;
les autres sont ignorés silencieusement (aucune fuite d'information). Si la liste
est vide, le bot est ouvert (utile en phase de test).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import get_settings
from bot.utils.logging_config import get_logger

log = get_logger("access")


class AccessMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.admin_ids = get_settings().admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.admin_ids:
            return await handler(event, data)  # bot ouvert

        user = data.get("event_from_user")
        if user is None or user.id not in self.admin_ids:
            log.debug("access.denied", user_id=getattr(user, "id", None))
            return None  # ignoré silencieusement
        return await handler(event, data)
