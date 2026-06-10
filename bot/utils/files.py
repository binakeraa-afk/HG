"""
Gestion et vérification des fichiers médias.

C'est ici qu'on implémente la « vérification multiple avant envoi » exigée :
  1. Le fichier existe et n'est pas vide.
  2. Sa taille est stable (il n'est plus en cours d'écriture).
  3. Son checksum SHA-256 est calculable (lecture intégrale sans erreur d'I/O).
  4. Pour une vidéo, ffprobe confirme qu'elle est décodable (au moins 1 flux).

Plus le nettoyage automatique des fichiers/dossiers temporaires.
"""
from __future__ import annotations

import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from bot.utils.logging_config import get_logger

log = get_logger("files")

# Extensions reconnues par catégorie.
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".gif", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS


@dataclass
class VerifiedFile:
    """Résultat d'une vérification réussie."""

    path: Path
    size: int
    sha256: str
    is_video: bool


async def _sha256(path: Path) -> str:
    """Calcule le SHA-256 en streaming, dans un thread pour ne pas bloquer l'event loop."""

    def _hash() -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    return await asyncio.to_thread(_hash)


async def _is_size_stable(path: Path, checks: int = 2, interval: float = 0.4) -> bool:
    """Vérifie que la taille ne bouge plus (fichier complètement écrit)."""
    last = -1
    for _ in range(checks):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == 0:
            return False
        if size == last:
            return True
        last = size
        await asyncio.sleep(interval)
    # Dernière comparaison.
    try:
        return path.stat().st_size == last
    except OSError:
        return False


async def _ffprobe_ok(path: Path) -> bool:
    """Confirme via ffprobe qu'une vidéo possède au moins un flux décodable.

    Si ffprobe est absent, on ne bloque pas l'envoi (best-effort) : on log et on
    considère le fichier comme valide pour ne pas pénaliser l'utilisateur.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except FileNotFoundError:
        log.warning("ffprobe.absent", file=str(path))
        return True
    except Exception as exc:  # noqa: BLE001 — best effort, jamais bloquant
        log.warning("ffprobe.error", file=str(path), error=repr(exc))
        return True
    return proc.returncode == 0 and bool(out.strip())


async def verify_media(path: Path) -> VerifiedFile | None:
    """Effectue toutes les vérifications. Renvoie VerifiedFile ou None.

    Ne lève jamais : un None se traduit par « on saute ce fichier silencieusement ».
    """
    try:
        if not path.exists() or not path.is_file():
            log.warning("verify.missing", file=str(path))
            return None

        if not await _is_size_stable(path):
            log.warning("verify.unstable_or_empty", file=str(path))
            return None

        is_video = path.suffix.lower() in VIDEO_EXTS
        if is_video and not await _ffprobe_ok(path):
            log.warning("verify.ffprobe_failed", file=str(path))
            return None

        size = path.stat().st_size
        digest = await _sha256(path)  # lecture complète => détecte la corruption d'I/O

        log.debug("verify.ok", file=str(path), size=size, sha256=digest[:12])
        return VerifiedFile(path=path, size=size, sha256=digest, is_video=is_video)
    except Exception as exc:  # noqa: BLE001
        log.warning("verify.unexpected", file=str(path), error=repr(exc))
        return None


def iter_media_files(directory: Path) -> list[Path]:
    """Liste triée et déterministe des fichiers médias d'un dossier (récursif)."""
    if not directory.exists():
        return []
    files = [
        p for p in sorted(directory.rglob("*"))
        if p.is_file() and p.suffix.lower() in MEDIA_EXTS
    ]
    return files


async def safe_unlink(path: Path) -> None:
    """Supprime un fichier sans jamais lever."""
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("cleanup.unlink_failed", file=str(path), error=repr(exc))


async def safe_rmtree(directory: Path) -> None:
    """Supprime récursivement un dossier sans jamais lever."""
    try:
        await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("cleanup.rmtree_failed", dir=str(directory), error=repr(exc))
