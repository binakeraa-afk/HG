"""
Agrégation des routeurs et branchement des middlewares.

L'ordre d'inclusion compte :
  1. errors  — doit voir toutes les erreurs.
  2. start / commands — commandes explicites prioritaires.
  3. callbacks — clics inline.
  4. profile_link — détection générique de lien (en dernier pour ne pas masquer
     les commandes).
"""
from __future__ import annotations

from aiogram import Dispatcher

from bot.handlers import callbacks, commands, errors, profile_link, start
from bot.middlewares import AccessMiddleware, ThrottlingMiddleware


def setup_handlers(dp: Dispatcher) -> None:
    """Branche middlewares + routeurs sur le dispatcher."""
    # Middlewares au niveau messages et callbacks.
    access = AccessMiddleware()
    throttle = ThrottlingMiddleware()

    dp.message.middleware(access)
    dp.message.middleware(throttle)
    dp.callback_query.middleware(access)

    # Routeurs (ordre significatif).
    dp.include_router(errors.router)
    dp.include_router(start.router)
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(profile_link.router)
