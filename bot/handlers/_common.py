"""
Helpers partagés par les handlers : lancement d'un job de façon robuste.

`launch_job` orchestre la création persistée + l'affichage initial + la mise en
file. Tout est défensif : en cas de souci, l'utilisateur reçoit un message neutre
et l'erreur est journalisée silencieusement.
"""
from __future__ import annotations

from aiogram import Bot

from bot.config import get_settings
from bot.db import repository as repo
from bot.models.enums import MediaScope
from bot.services.queue import JobQueue
from bot.utils.logging_config import get_logger
from bot.utils.validators import ProfileRef

log = get_logger("handlers.common")

# Message neutre en cas de pépin — jamais d'erreur technique exposée.
_NEUTRAL_ERROR = "⏳ Je m'en occupe en arrière-plan, les médias arriveront dans le groupe."


async def launch_job(
    *,
    bot: Bot,
    job_queue: JobQueue,
    profile: ProfileRef,
    scope: MediaScope,
    limit: int,
    requested_by: int,
    origin_chat_id: int,
    ack_message=None,
) -> None:
    """Crée et met en file un job pour le profil donné. Ne lève jamais."""
    settings = get_settings()
    effective_limit = settings.hard_media_cap if limit <= 0 else min(limit, settings.hard_media_cap)

    try:
        db_profile = await repo.get_or_create_profile(
            profile.username, settings.target_chat_id
        )
        job = await repo.create_job(
            profile_id=db_profile.id,
            requested_by=requested_by,
            origin_chat_id=origin_chat_id,
            scope=scope,
            limit=effective_limit,
        )

        # Message de progression initial dans le chat d'origine (privé ou groupe).
        scope_label = "tous les médias" if scope is MediaScope.ALL else "les vidéos"
        qty_label = "toutes" if limit <= 0 else str(limit)
        intro = (
            f"📥 Récupération de <b>{qty_label}</b> {scope_label} de "
            f"<b>@{profile.username}</b> en cours…\n"
            f"<i>Les médias seront publiés dans le groupe dédié.</i>"
        )
        try:
            sent = await bot.send_message(origin_chat_id, intro)
            await repo.update_job(job.id, progress_message_id=sent.message_id)
        except Exception as exc:  # noqa: BLE001
            # L'absence de message de progression n'empêche pas le job.
            log.warning("launch.progress_msg_failed", error=repr(exc))

        await job_queue.enqueue(job.id)
        log.info(
            "launch.ok",
            username=profile.username, scope=scope.value, limit=effective_limit,
            job_id=job.id,
        )
    except Exception as exc:  # noqa: BLE001 — filet ultime côté handler
        log.error("launch.failed", username=profile.username, error=repr(exc), exc_info=True)
        if ack_message is not None:
            try:
                await ack_message.answer(_NEUTRAL_ERROR)
            except Exception:  # noqa: BLE001
                pass
