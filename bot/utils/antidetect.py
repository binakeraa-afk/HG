"""
Stratégies anti-détection / anti-blocage pour X.

⚠️ Cadre d'usage : ce module sert à récupérer de façon FIABLE des médias PUBLICS
d'un profil que l'on a le droit de consulter, en lissant la charge pour ne pas se
faire rate-limiter. Il ne contourne aucune authentification et n'attaque rien.

Techniques implémentées :
  - Rotation d'User-Agents réalistes.
  - Pool de proxys avec rotation (round-robin + retrait temporaire d'un proxy KO).
  - Délais aléatoires entre requêtes (jitter humain).
  - Centralisation des cookies X (session connectée fournie par l'opérateur).
"""
from __future__ import annotations

import asyncio
import itertools
import random
import time

from bot.config import get_settings
from bot.utils.logging_config import get_logger

log = get_logger("antidetect")

# Panel d'User-Agents desktop récents et plausibles.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class ProxyPool:
    """Pool de proxys à rotation, avec mise en quarantaine des proxys défaillants."""

    def __init__(self, proxies: list[str], cooldown: float = 120.0) -> None:
        self._all = list(proxies)
        self._cycle = itertools.cycle(self._all) if self._all else None
        self._cooldown = cooldown
        # proxy -> timestamp jusqu'auquel il est en quarantaine
        self._quarantine: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._all)

    async def acquire(self) -> str | None:
        """Renvoie le prochain proxy disponible, ou None si aucun n'est configuré."""
        if not self._cycle:
            return None
        async with self._lock:
            now = time.monotonic()
            # On tente au plus len(_all) proxys pour en trouver un hors quarantaine.
            for _ in range(len(self._all)):
                candidate = next(self._cycle)
                until = self._quarantine.get(candidate, 0.0)
                if until <= now:
                    return candidate
            # Tous en quarantaine : on prend le « moins pire ».
            return min(self._quarantine, key=self._quarantine.get, default=None)

    async def report_failure(self, proxy: str | None) -> None:
        """Met un proxy en quarantaine après un échec."""
        if not proxy:
            return
        async with self._lock:
            self._quarantine[proxy] = time.monotonic() + self._cooldown
            log.warning("proxy.quarantined", proxy=_mask(proxy), seconds=self._cooldown)


class AntiDetect:
    """Façade regroupant toutes les primitives anti-blocage."""

    def __init__(self) -> None:
        settings = get_settings()
        self.proxies = ProxyPool(settings.proxy_list)
        self._min_delay = settings.min_request_delay
        self._max_delay = settings.max_request_delay
        self._settings = settings

    def random_user_agent(self) -> str:
        return random.choice(_USER_AGENTS)

    async def human_delay(self) -> None:
        """Pause aléatoire imitant un comportement humain entre deux requêtes."""
        delay = random.uniform(self._min_delay, self._max_delay)
        await asyncio.sleep(delay)

    def cookies_path(self) -> str | None:
        """Chemin du fichier cookies (fichier ou contenu via variable d'env)."""
        return self._settings.cookies_file_path()


def _mask(proxy: str) -> str:
    """Masque les identifiants d'un proxy pour les logs."""
    if "@" in proxy:
        return "***@" + proxy.split("@", 1)[1]
    return proxy


# Instance partagée (les primitives sont thread/async-safe).
antidetect = AntiDetect()
