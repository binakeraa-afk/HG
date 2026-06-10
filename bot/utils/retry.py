"""
Système de retry maison : backoff exponentiel + jitter.

Objectifs (exigences du cahier des charges) :
  - Jusqu'à N tentatives (5 par défaut).
  - Délai exponentiel borné (RETRY_BASE_DELAY * 2**n), plafonné à RETRY_MAX_DELAY.
  - Jitter aléatoire pour éviter les « thundering herds ».
  - Respect des délais imposés par l'API (FloodWait Telegram, Retry-After HTTP).
  - Aucune exception ne fuit : à l'épuisement des tentatives on lève une exception
    contrôlée que l'appelant peut capturer silencieusement.

On fournit à la fois un décorateur (`async_retry`) et une fonction utilitaire
(`retry_call`) pour les cas où le décorateur est trop rigide.
"""
from __future__ import annotations

import asyncio
import functools
import random
from typing import Awaitable, Callable, Iterable, TypeVar

from bot.config import get_settings
from bot.utils.logging_config import get_logger

log = get_logger("retry")

T = TypeVar("T")


class RetryExhausted(Exception):
    """Levée quand toutes les tentatives ont échoué. Toujours capturée en amont."""

    def __init__(self, attempts: int, last_exc: BaseException) -> None:
        super().__init__(f"Échec après {attempts} tentative(s) : {last_exc!r}")
        self.attempts = attempts
        self.last_exc = last_exc


def _extract_retry_after(exc: BaseException) -> float | None:
    """Tente d'extraire un délai imposé par le serveur depuis l'exception.

    Couvre aiogram (TelegramRetryAfter.retry_after) et les exceptions HTTP
    portant un attribut `retry_after` / `retry-after`.
    """
    for attr in ("retry_after", "timeout"):
        val = getattr(exc, attr, None)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    return None


def _compute_delay(attempt: int, base: float, cap: float) -> float:
    """Calcule un délai exponentiel avec jitter complet (« full jitter »)."""
    raw = min(cap, base * (2 ** attempt))
    return random.uniform(0, raw)


async def retry_call(
    func: Callable[..., Awaitable[T]],
    *args,
    retry_on: Iterable[type[BaseException]] = (Exception,),
    give_up_on: Iterable[type[BaseException]] = (),
    max_attempts: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    op_name: str = "operation",
    **kwargs,
) -> T:
    """Exécute `func(*args, **kwargs)` avec retries.

    :param retry_on: exceptions qui déclenchent une nouvelle tentative.
    :param give_up_on: exceptions qui arrêtent immédiatement (pas de retry).
    :raises RetryExhausted: si toutes les tentatives échouent.
    """
    settings = get_settings()
    attempts = max_attempts or settings.max_retries
    base = base_delay if base_delay is not None else settings.retry_base_delay
    cap = max_delay if max_delay is not None else settings.retry_max_delay

    retry_on = tuple(retry_on)
    give_up_on = tuple(give_up_on)
    last_exc: BaseException = RuntimeError("aucune tentative exécutée")

    for attempt in range(attempts):
        try:
            return await func(*args, **kwargs)
        except give_up_on as exc:  # type: ignore[misc]
            log.warning("retry.give_up", op=op_name, error=repr(exc))
            raise
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            # Le serveur a-t-il imposé un délai ? On le respecte en priorité.
            forced = _extract_retry_after(exc)
            delay = forced if forced is not None else _compute_delay(attempt, base, cap)
            is_last = attempt == attempts - 1
            log.warning(
                "retry.attempt_failed",
                op=op_name,
                attempt=attempt + 1,
                max_attempts=attempts,
                delay=round(delay, 2),
                forced=forced is not None,
                error=repr(exc),
                will_retry=not is_last,
            )
            if is_last:
                break
            await asyncio.sleep(delay)

    raise RetryExhausted(attempts, last_exc)


def async_retry(
    *,
    retry_on: Iterable[type[BaseException]] = (Exception,),
    give_up_on: Iterable[type[BaseException]] = (),
    max_attempts: int | None = None,
    op_name: str | None = None,
):
    """Décorateur appliquant `retry_call` à une coroutine."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        name = op_name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_call(
                func,
                *args,
                retry_on=retry_on,
                give_up_on=give_up_on,
                max_attempts=max_attempts,
                op_name=name,
                **kwargs,
            )

        return wrapper

    return decorator
