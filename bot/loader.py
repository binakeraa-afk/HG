"""
Fabriques des objets aiogram centraux (Bot, Dispatcher).

On isole la création ici pour éviter les imports circulaires et faciliter les tests.
Le stockage FSM est en mémoire (suffisant : l'état durable vit en base, pas en FSM).
"""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_settings


def create_bot() -> Bot:
    """Crée l'instance Bot avec des réglages par défaut sûrs."""
    settings = get_settings()
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )


def create_dispatcher() -> Dispatcher:
    """Crée le Dispatcher (routeurs et middlewares branchés ailleurs)."""
    return Dispatcher(storage=MemoryStorage())
