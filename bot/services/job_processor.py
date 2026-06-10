"""
JobProcessor : orchestration complète d'un job, de bout en bout.

Pipeline :
  1. RESOLVING  : garantit le topic du profil + prépare le dossier de travail.
  2. DOWNLOADING: lance le backend d'extraction (yt-dlp / gallery-dl).
  3. SENDING    : pour chaque fichier → vérifie → envoie → marque SENT → supprime.
  4. COMPLETED  : nettoyage du dossier + message final.

Robustesse :
  - Chaque étape est protégée ; une exception non prévue fait passer le job en
    FAILED avec log détaillé, jamais de crash du worker.
  - Idempotence : un média déjà SENT (clé stable) n'est jamais renvoyé, ce qui
    rend la reprise après redémarrage sûre.
  - Nettoyage garanti via `finally`.
"""
from __future__ import annotations

from pathlib import Path

from aiogram import Bot

from bot.config import get_settings
from bot.db import repository as repo
from bot.models import Job
from bot.models.enums import JobStatus, MediaKind, MediaStatus
from bot.services.extractor import get_extractor
from bot.services.media_sender import MediaSender
from bot.services.progress import ProgressReporter
from bot.services.topic_manager import TopicManager
from bot.utils.files import VIDEO_EXTS, safe_rmtree, safe_unlink
from bot.utils.logging_config import get_logger
from bot.utils.retry import retry_call

log = get_logger("job_processor")


class JobProcessor:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self.sender = MediaSender(bot)
        self.topics = TopicManager(bot)

    async def process(self, job_id: int) -> None:
        """Point d'entrée appelé par un worker. Ne lève jamais."""
        job = await repo.get_job(job_id)
        if job is None:
            log.warning("job.not_found", job_id=job_id)
            return
        if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return

        # Lie le contexte de log à ce job (apparaît dans chaque ligne).
        import structlog

        structlog.contextvars.bind_contextvars(job_id=job_id, profile_id=job.profile_id)

        username = await self._username_of(job.profile_id)
        reporter = ProgressReporter(self.bot, job.origin_chat_id, job.progress_message_id)
        work_dir = self.settings.work_dir / f"job_{job_id}"

        try:
            await repo.update_job(
                job_id, status=JobStatus.RESOLVING, attempts=job.attempts + 1,
                work_subdir=str(work_dir),
            )
            await reporter.update(
                username=username, phase="Préparation…", found=0, sent=0, failed=0,
                force=True,
            )

            topic_id = await self.topics.ensure_topic(job.profile_id, username)

            # ── Téléchargement ────────────────────────────────────────────────
            await repo.update_job(job_id, status=JobStatus.DOWNLOADING)
            await reporter.update(
                username=username, phase="Téléchargement…", found=0, sent=0, failed=0,
                force=True,
            )
            files = await self._download(job, username, work_dir)
            await repo.update_job(job_id, total_found=len(files))

            # ── Envoi ─────────────────────────────────────────────────────────
            await repo.update_job(job_id, status=JobStatus.SENDING)
            sent, failed = await self._send_all(
                job, username, topic_id, files, reporter
            )

            await repo.update_job(
                job_id, status=JobStatus.COMPLETED, sent_count=sent, failed_count=failed,
            )
            await reporter.finalize(username=username, sent=sent, failed=failed)
            log.info("job.completed", username=username, sent=sent, failed=failed)

        except Exception as exc:  # noqa: BLE001 — filet ultime du pipeline
            log.error("job.failed", username=username, error=repr(exc), exc_info=True)
            await repo.update_job(job_id, status=JobStatus.FAILED, last_error=repr(exc)[:500])
            await reporter.update(
                username=username,
                phase="Réessai automatique ultérieur…",
                found=job.total_found, sent=job.sent_count, failed=job.failed_count,
                force=True,
            )
        finally:
            await safe_rmtree(work_dir)
            structlog.contextvars.clear_contextvars()

    # ── Étapes internes ─────────────────────────────────────────────────────--

    async def _download(self, job: Job, username: str, work_dir: Path) -> list[Path]:
        """Télécharge les médias, avec retry global sur l'extraction."""
        extractor = get_extractor(job.scope)
        # Les deux backends partent de la timeline « médias » du profil.
        media_url = f"https://x.com/{username}/media"
        limit = min(job.limit, self.settings.hard_media_cap)

        async def _run() -> list[Path]:
            files = await extractor.extract(media_url, work_dir, limit)
            if not files:
                # Aucun fichier => on lève pour déclencher le backoff/retry.
                raise RuntimeError("aucun média téléchargé")
            return files

        try:
            return await retry_call(
                _run, op_name="extract", retry_on=(Exception,),
            )
        except Exception as exc:  # noqa: BLE001
            # Échec total d'extraction : on renvoie ce qui traîne (souvent rien).
            from bot.utils.files import iter_media_files
            log.warning("download.empty", username=username, error=repr(exc))
            return iter_media_files(work_dir)

    async def _send_all(
        self,
        job: Job,
        username: str,
        topic_id: int | None,
        files: list[Path],
        reporter: ProgressReporter,
    ) -> tuple[int, int]:
        """Envoie tous les fichiers un par un avec vérif + dédup + nettoyage."""
        sent = job.sent_count
        failed = job.failed_count
        total = len(files)

        for index, path in enumerate(files, start=1):
            stable_key = self._stable_key(path)

            # Idempotence : déjà envoyé ? On saute et on supprime le doublon local.
            if await repo.is_media_sent(job.profile_id, stable_key):
                await safe_unlink(path)
                continue

            is_video = path.suffix.lower() in VIDEO_EXTS
            kind = MediaKind.VIDEO if is_video else MediaKind.PHOTO

            result = await self.sender.send_file(
                path=path,
                chat_id=self.settings.target_chat_id,
                topic_id=topic_id,
                caption=None,
            )

            if result.ok:
                sent += 1
                await repo.upsert_media(
                    profile_id=job.profile_id, job_id=job.id, stable_key=stable_key,
                    kind=kind, status=MediaStatus.SENT, tg_file_id=result.file_id,
                    source_url=f"https://x.com/{username}",
                )
                await repo.increment_job_counter(job.id, "sent_count", 1)
            else:
                failed += 1
                await repo.upsert_media(
                    profile_id=job.profile_id, job_id=job.id, stable_key=stable_key,
                    kind=kind, status=MediaStatus.FAILED,
                )
                await repo.increment_job_counter(job.id, "failed_count", 1)

            # Nettoyage immédiat du fichier envoyé (gestion fine de l'espace disque).
            await safe_unlink(path)

            await reporter.update(
                username=username, phase=f"Envoi {index}/{total}",
                found=total, sent=sent, failed=failed,
            )

        return sent, failed

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _stable_key(path: Path) -> str:
        """Clé stable/déterministe d'un média à partir de son nom de fichier.

        yt-dlp et gallery-dl incluent l'id de tweet dans le nom de fichier, ce qui
        nous donne une clé naturellement déduplicable.
        """
        return path.stem[:128]

    async def _username_of(self, profile_id: int) -> str:
        from bot.db.engine import session_scope
        from bot.models import Profile
        from sqlalchemy import select

        async with session_scope() as s:
            res = await s.execute(select(Profile.username).where(Profile.id == profile_id))
            return res.scalar_one_or_none() or "inconnu"
