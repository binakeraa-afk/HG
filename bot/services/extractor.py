"""Extraction / téléchargement des médias depuis X (backend gallery-dl)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from bot.config import get_settings
from bot.models.enums import MediaScope
from bot.utils.antidetect import antidetect
from bot.utils.files import iter_media_files
from bot.utils.logging_config import get_logger

log = get_logger("extractor")
_EXTRACTION_TIMEOUT = 60 * 30  # 30 minutes


class GalleryDlExtractor:
    """gallery-dl : télécharge les médias d'une timeline de profil X."""

    name = "gallery-dl"

    def __init__(self) -> None:
        self.settings = get_settings()

    def build_command(self, media_url: str, dest: Path, limit: int, proxy: str | None) -> list[str]:
        cmd = [
            "gallery-dl",
            "--range", f"1-{limit}",
            "--directory", str(dest),
            "--retries", "5",
            "--user-agent", antidetect.random_user_agent(),
            "-o", "extractor.twitter.videos=true",
            "-o", "extractor.twitter.text-tweets=false",
        ]
        cookies = antidetect.cookies_path()
        if cookies:
            cmd += ["--cookies", cookies]
        if proxy:
            cmd += ["--proxy", proxy]
        cmd.append(media_url)
        return cmd

    async def extract(self, media_url: str, dest: Path, limit: int) -> list[Path]:
        dest.mkdir(parents=True, exist_ok=True)
        await antidetect.human_delay()
        proxy = await antidetect.proxies.acquire()

        cmd = self.build_command(media_url, dest, limit, proxy)
        log.info("extractor.start", backend=self.name, url=media_url, limit=limit, proxy=bool(proxy))

        returncode, stderr_tail = await self._run_subprocess(cmd)

        files = iter_media_files(dest)
        if returncode != 0:
            log.warning(
                "extractor.nonzero_exit",
                backend=self.name, code=returncode, produced=len(files), stderr=stderr_tail,
            )
            if not files:
                await antidetect.proxies.report_failure(proxy)

        log.info("extractor.done", backend=self.name, files=len(files))
        return files

    async def _run_subprocess(self, cmd: list[str]) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            log.error("extractor.binary_missing", backend=self.name, error=repr(exc))
            return 127, str(exc)
        except Exception as exc:
            log.error("extractor.spawn_failed", backend=self.name, error=repr(exc))
            return 1, str(exc)

        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_EXTRACTION_TIMEOUT)
        except asyncio.TimeoutError:
            log.error("extractor.timeout", backend=self.name)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return 124, "timeout"

        tail = (stderr or b"").decode("utf-8", "replace")[-800:]
        return proc.returncode or 0, tail


def get_extractor(scope: MediaScope) -> GalleryDlExtractor:
    """Backend d'extraction (le périmètre est appliqué par filtrage dans job_processor)."""
    return GalleryDlExtractor()
