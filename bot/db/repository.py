"""
Repository : toutes les opérations CRUD passent par ici.

Avantages :
  - Le reste du code ne connaît pas SQLAlchemy en détail.
  - Chaque opération est défensive et journalisée.
  - Facile à tester / remplacer.
"""
from __future__ import annotations

from sqlalchemy import select, update

from bot.db.engine import session_scope
from bot.models import Job, MediaItem, Profile
from bot.models.enums import JobStatus, MediaKind, MediaScope, MediaStatus
from bot.utils.logging_config import get_logger

log = get_logger("repository")

# ── Profils ──────────────────────────────────────────────────────────────────


async def get_or_create_profile(username: str, chat_id: int) -> Profile:
    """Récupère le profil par username (insensible à la casse) ou le crée."""
    async with session_scope() as s:
        res = await s.execute(
            select(Profile).where(Profile.username.ilike(username))
        )
        profile = res.scalar_one_or_none()
        if profile is None:
            profile = Profile(username=username, chat_id=chat_id)
            s.add(profile)
            await s.flush()
            log.info("profile.created", username=username, id=profile.id)
        # On détache un objet « simple » pour usage hors session.
        await s.refresh(profile)
        s.expunge(profile)
        return profile


async def set_profile_topic(profile_id: int, topic_id: int | None) -> None:
    async with session_scope() as s:
        await s.execute(
            update(Profile).where(Profile.id == profile_id).values(topic_id=topic_id)
        )


# ── Jobs ─────────────────────────────────────────────────────────────────────


async def create_job(
    *,
    profile_id: int,
    requested_by: int,
    origin_chat_id: int,
    scope: MediaScope,
    limit: int,
) -> Job:
    async with session_scope() as s:
        job = Job(
            profile_id=profile_id,
            requested_by=requested_by,
            origin_chat_id=origin_chat_id,
            scope=scope,
            limit=limit,
            status=JobStatus.PENDING,
        )
        s.add(job)
        await s.flush()
        await s.refresh(job)
        s.expunge(job)
        log.info("job.created", job_id=job.id, profile_id=profile_id, scope=scope.value)
        return job


async def update_job(job_id: int, **values) -> None:
    """Met à jour partiellement un job. Ne lève pas si le job n'existe plus."""
    if not values:
        return
    async with session_scope() as s:
        await s.execute(update(Job).where(Job.id == job_id).values(**values))


async def increment_job_counter(job_id: int, field: str, by: int = 1) -> None:
    """Incrémente atomiquement un compteur de progression."""
    async with session_scope() as s:
        col = getattr(Job, field)
        await s.execute(update(Job).where(Job.id == job_id).values({col: col + by}))


async def get_job(job_id: int) -> Job | None:
    async with session_scope() as s:
        res = await s.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()
        if job is not None:
            s.expunge(job)
        return job


async def get_resumable_jobs() -> list[Job]:
    """Jobs non terminaux à requeue après un redémarrage."""
    active = {
        JobStatus.PENDING,
        JobStatus.RESOLVING,
        JobStatus.DOWNLOADING,
        JobStatus.SENDING,
    }
    async with session_scope() as s:
        res = await s.execute(select(Job).where(Job.status.in_(active)))
        jobs = list(res.scalars().all())
        for j in jobs:
            s.expunge(j)
        return jobs


# ── Médias ───────────────────────────────────────────────────────────────────


async def is_media_sent(profile_id: int, stable_key: str) -> bool:
    """True si ce média a déjà été envoyé (idempotence / reprise)."""
    async with session_scope() as s:
        res = await s.execute(
            select(MediaItem.status).where(
                MediaItem.profile_id == profile_id,
                MediaItem.stable_key == stable_key,
            )
        )
        status = res.scalar_one_or_none()
        return status == MediaStatus.SENT


async def get_sent_file_id(profile_id: int, stable_key: str) -> str | None:
    """Renvoie le file_id Telegram si le média a déjà été uploadé (renvoi gratuit)."""
    async with session_scope() as s:
        res = await s.execute(
            select(MediaItem.tg_file_id).where(
                MediaItem.profile_id == profile_id,
                MediaItem.stable_key == stable_key,
                MediaItem.status == MediaStatus.SENT,
            )
        )
        return res.scalar_one_or_none()


async def upsert_media(
    *,
    profile_id: int,
    job_id: int,
    stable_key: str,
    kind: MediaKind,
    status: MediaStatus,
    **extra,
) -> None:
    """Insère ou met à jour un média par (profile_id, stable_key)."""
    async with session_scope() as s:
        res = await s.execute(
            select(MediaItem).where(
                MediaItem.profile_id == profile_id,
                MediaItem.stable_key == stable_key,
            )
        )
        item = res.scalar_one_or_none()
        if item is None:
            item = MediaItem(
                profile_id=profile_id,
                job_id=job_id,
                stable_key=stable_key,
                kind=kind,
                status=status,
                **extra,
            )
            s.add(item)
        else:
            item.status = status
            item.job_id = job_id
            for k, v in extra.items():
                setattr(item, k, v)
