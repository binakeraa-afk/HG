"""
Extraction / téléchargement des médias depuis X.

Deux backends complémentaires, choisis selon le périmètre demandé :

  • YtDlpExtractor  → périmètre VIDEOS (lien de profil).
                      yt-dlp est très fiable pour extraire les vidéos d'une
                      timeline « /media ».

  • GalleryDlExtractor → périmètre ALL (/allmedia : photos + vidéos).
                      gallery-dl gère parfaitement les galeries média d'un profil
                      X (images + vidéos), avec archive de déduplication.

Chaque backend :
  - s'exécute en sous-processus (isolation des crashs natifs),
  - applique les options anti-détection (cookies, user-agent, proxy, délais),
  - télécharge dans le dossier de travail du job,
  - renvoie la liste des fichiers médias produits.

Aucune exception ne remonte : en cas de problème on renvoie ce qui a pu être
téléchargé (souvent partiel) et on journalise tout.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from bot.config import get_settings
from bot.models.enums import MediaScope
from bot.utils.antidetect import antidetect
from bot.utils.files import iter_media_files
from bot.utils.logging_config import get_logger

log = get_logger("extractor")

# Délai max accordé à une extraction complète (garde-fou anti-blocage).
_EXTRACTION_TIMEOUT = 60 * 30  # 30 minutes


class BaseExtractor(ABC):
    """Contrat commun aux backends d'extraction."""

    name: str = "base"

    def __init__(self) -> None:
        self.settings = get_settings()

    @abstractmethod
    def build_command(
        self, media_url: str, dest: Path, limit: int, proxy: str | None
    ) -> list[str]:
        """Construit la ligne de commande du backend."""

    async def extract(self, media_url: str, dest: Path, limit: int) -> list[Path]:
        """Lance le téléchargement et renvoie les fichiers médias produits."""
        dest.mkdir(parents=True, exist_ok=True)

        # Anti-détection : on patiente un délai « humain » et on prend un proxy.
        await antidetect.human_delay()
        proxy = await antidetect.proxies.acquire()

        cmd = self.build_command(media_url, dest, limit, proxy)
        log.info(
            "extractor.start",
            backend=self.name,
            url=media_url,
            limit=limit,
            proxy=bool(proxy),
        )

        returncode, stderr_tail = await self._run_subprocess(cmd)

        files = iter_media_files(dest)
        if returncode != 0:
            # Un code non nul est fréquent (certains médias indisponibles) :
            # on ne considère ça comme un échec que si RIEN n'a été récupéré.
            log.warning(
                "extractor.nonzero_exit",
                backend=self.name,
                code=returncode,
                produced=len(files),
                stderr=stderr_tail,
            )
            if not files:
                await antidetect.proxies.report_failure(proxy)

        log.info("extractor.done", backend=self.name, files=len(files))
        return files

    async def _run_subprocess(self, cmd: list[str]) -> tuple[int, str]:
        """Exécute la commande, capture la sortie, applique un timeout dur."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            log.error("extractor.binary_missing", backend=self.name, error=repr(exc))
            return 127, str(exc)
        except Exception as exc:  # noqa: BLE001
            log.error("extractor.spawn_failed", backend=self.name, error=repr(exc))
            return 1, str(exc)

        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_EXTRACTION_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.error("extractor.timeout", backend=self.name)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return 124, "timeout"

        tail = (stderr or b"").decode("utf-8", "replace")[-800:]
        return proc.returncode or 0, tail


class YtDlpExtractor(BaseExtractor):
    """Backend vidéos basé sur yt-dlp."""

    name = "yt-dlp"

    def build_command(
        self, media_url: str, dest: Path, limit: int, proxy: str | None
    ) -> list[str]:
        out_tmpl = str(dest / "%(id)s_%(autonumber)03d.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--ignore-errors",          # ne s'arrête pas sur un média KO
            "--no-playlist-reverse",
            "--playlist-end", str(limit),
            "--retries", "5",
            "--fragment-retries", "5",
            "--socket-timeout", "30",
            "--concurrent-fragments", "4",
            # On force un conteneur mp4 lisible partout (Telegram).
            "--merge-output-format", "mp4",
            "--user-agent", antidetect.random_user_agent(),
            "-o", out_tmpl,
        ]
        cookies = antidetect.cookies_path()
        if cookies:
            cmd += ["--cookies", cookies]
        if proxy:
            cmd += ["--proxy", proxy]
        cmd.append(media_url)
        return cmd


class GalleryDlExtractor(BaseExtractor):
    """Backend tous-médias basé sur gallery-dl."""

    name = "gallery-dl"

    def build_command(
        self, media_url: str, dest: Path, limit: int, proxy: str | None
    ) -> list[str]:
        cmd = [
            "gallery-dl",
            "--range", f"1-{limit}",
            "--directory", str(dest),     # destination plate
            "--retries", "5",
            "--user-agent", antidetect.random_user_agent(),
            # On inclut les vidéos en plus des images pour le périmètre « tous médias ».
            # NB : pas d'archive cross-job ici — la déduplication d'envoi se fait en
            # base (is_media_sent) pour garantir une reprise correcte après crash.
            "-o", "extractor.twitter.videos=true",
        ]
        cookies = antidetect.cookies_path()
        if cookies:
            cmd += ["--cookies", cookies]
        if proxy:
            cmd += ["--proxy", proxy]
        cmd.append(media_url)
        return cmd


def get_extractor(scope: MediaScope) -> BaseExtractor:
    """Sélectionne le backend adapté au périmètre demandé."""
    if scope is MediaScope.ALL:
        return GalleryDlExtractor()
    return YtDlpExtractor()
