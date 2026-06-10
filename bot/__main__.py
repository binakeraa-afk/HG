"""
Point d'entrée du bot.

Séquence de démarrage :
  1. Logging structuré.
  2. Base de données (moteur + schéma).
  3. Bot + Dispatcher + handlers/middlewares.
  4. File d'attente + pool de workers.
  5. Reprise des jobs non terminés (résilience après redémarrage).
  6. Long-polling Telegram.

Arrêt propre : drainage de la file, fermeture du pool DB et de la session HTTP.
Tout est encadré pour qu'aucune erreur ne provoque un crash silencieux non logué.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from bot.config import get_settings
from bot.db.engine import dispose_engine, init_engine
from bot.handlers import setup_handlers
from bot.loader import create_bot, create_dispatcher
from bot.services.queue import JobQueue
from bot.utils.logging_config import get_logger, setup_logging


async def _set_commands(bot: Bot) -> None:
    """Renseigne le menu des commandes Telegram (best-effort)."""
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Démarrer / aide"),
                BotCommand(command="allmedia", description="Tous les médias d'un profil"),
                BotCommand(command="help", description="Aide"),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        get_logger("startup").warning("set_commands_failed", error=repr(exc))


async def main() -> None:
    setup_logging()
    log = get_logger("main")
    settings = get_settings()

    log.info("boot.start", version="1.0.0")

    # 1) Base de données.
    await init_engine()

    # 2) Bot + Dispatcher.
    bot = create_bot()
    dp = create_dispatcher()
    setup_handlers(dp)

    # 3) File d'attente (injectée dans les handlers via workflow_data).
    job_queue = JobQueue(bot)
    dp["job_queue"] = job_queue

    # 4) Hooks de cycle de vie.
    async def on_startup() -> None:
        await _set_commands(bot)
        await job_queue.start()
        resumed = await job_queue.requeue_pending()
        log.info("boot.ready", resumed_jobs=resumed)

    async def on_shutdown() -> None:
        log.info("shutdown.start")
        await job_queue.stop()
        await dispose_engine()
        await bot.session.close()
        log.info("shutdown.done")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # 5) Long-polling. aiogram gère SIGINT/SIGTERM et déclenche on_shutdown.
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            handle_signals=True,
        )
    except Exception as exc:  # noqa: BLE001 — on log même un crash du polling
        log.error("polling.crashed", error=repr(exc), exc_info=True)
        raise


def run() -> None:
    """Wrapper synchrone pour `python -m bot`."""
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    run()
