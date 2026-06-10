"""
Configuration du logging structuré (structlog).
"""
from __future__ import annotations

import logging
import sys

import structlog

from bot.config import get_settings


def setup_logging() -> None:
    """Initialise structlog + la stdlib logging. À appeler une fois au démarrage."""
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    # ⚠️ Aucun processeur ne doit dépendre d'un attribut du logger (ex: .name),
    # car PrintLogger ne le fournit pas.
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
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

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=level)
    for noisy in ("aiosqlite", "asyncio", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None):
    """Logger structuré 'nommé' : le nom est injecté comme champ `logger`."""
    logger = structlog.get_logger()
    if name:
        return logger.bind(logger=name)
    return logger
