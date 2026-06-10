"""
File d'attente de jobs + pool de workers asynchrones.

Caractéristiques :
  - `asyncio.Queue` borné par un sémaphore de concurrence (WORKER_CONCURRENCY).
  - Plusieurs profils traités EN PARALLÈLE sans interférence (chacun a son dossier
    de travail, son topic, ses lignes en base).
  - Reprise après redémarrage : `requeue_pending()` recharge depuis la base tous
    les jobs non terminaux et les replace dans la file.
  - Arrêt propre : `stop()` attend la fin des tâches en cours.

C'est volontairement une file *en mémoire* alimentée par une *source persistante*
(la base). La base reste la source de vérité ; la file n'est qu'un tampon d'exécution.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot

from bot.config import get_settings
from bot.db import repository as repo
from bot.services.job_processor import JobProcessor
from bot.utils.logging_config import get_logger

log = get_logger("queue")


class JobQueue:
    def __init__(self, bot: Bot) -> None:
        self.settings = get_settings()
        self.processor = JobProcessor(bot)
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        # Évite qu'un même job_id soit traité deux fois simultanément.
        self._inflight: set[int] = set()
        self._lock = asyncio.Lock()

    # ── Cycle de vie ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Démarre le pool de workers."""
        if self._running:
            return
        self._running = True
        for i in range(self.settings.worker_concurrency):
            task = asyncio.create_task(self._worker(i), name=f"worker-{i}")
            self._workers.append(task)
        log.info("queue.started", workers=len(self._workers))

    async def stop(self) -> None:
        """Arrête proprement : on attend le drainage puis on annule les workers."""
        self._running = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=30)
        except asyncio.TimeoutError:
            log.warning("queue.drain_timeout")
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        log.info("queue.stopped")

    # ── Soumission ───────────────────────────────────────────────────────────

    async def enqueue(self, job_id: int) -> None:
        """Ajoute un job à la file (dédupliqué)."""
        async with self._lock:
            if job_id in self._inflight:
                return
            self._inflight.add(job_id)
        await self._queue.put(job_id)
        log.info("queue.enqueued", job_id=job_id, depth=self._queue.qsize())

    async def requeue_pending(self) -> int:
        """Recharge les jobs non terminaux depuis la base (reprise au boot)."""
        jobs = await repo.get_resumable_jobs()
        for job in jobs:
            await self.enqueue(job.id)
        if jobs:
            log.info("queue.requeued", count=len(jobs))
        return len(jobs)

    # ── Boucle de travail ────────────────────────────────────────────────────

    async def _worker(self, index: int) -> None:
        """Boucle d'un worker : prend un job, le traite, marque la tâche terminée."""
        log.info("worker.online", worker=index)
        while True:
            job_id = await self._queue.get()
            try:
                # Le JobProcessor ne lève jamais : double filet quand même.
                await self.processor.process(job_id)
            except Exception as exc:  # noqa: BLE001
                log.error("worker.unexpected", worker=index, job_id=job_id, error=repr(exc))
            finally:
                async with self._lock:
                    self._inflight.discard(job_id)
                self._queue.task_done()
