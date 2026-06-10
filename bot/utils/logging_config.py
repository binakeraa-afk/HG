"""
Configuration du logging structuré (structlog).

Philosophie :
  - Tout est logué, en détail, avec contexte (job_id, profil, étape...).
  - En production (LOG_JSON=true) la sortie est du JSON, idéal pour l'agrégateur
    de logs de Railway.
  - En local on garde un rendu coloré lisible.
  - AUCUN de ces logs ne remonte à l'utilisateur Telegram : ils restent côté serveur.
"""
from __future__ import annotations

import logging
import sys

import structlog

from bot.config import get_settings


def setup_logging() -> None:
    """Initialise structlog + la stdlib logging de façon cohérente.

    À appeler une seule fois, au tout début du démarrage.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    # Processeurs communs : ils enrichissent chaque évènement de log.
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,   # contexte attaché par tâche
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,       # sérialise les exceptions
    ]

    if settings.log_json:
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # On branche aussi la stdlib logging (aiogram, sqlalchemy...) sur le même flux.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
    )
    # On calme les bibliothèques bavardes pour ne garder que l'essentiel.
    for noisy in ("aiosqlite", "asyncio", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Raccourci pour obtenir un logger structuré nommé."""
    return structlog.get_logger(name)
