"""
Commande /allmedia : récupère TOUS les médias (photos + vidéos) d'un profil.

Usages acceptés :
  • /allmedia https://x.com/username
  • /allmedia https://x.com/username 100
  • /allmedia username
  • en réponse à un message contenant un lien X

Si aucun profil n'est trouvable, on répond par un message d'aide neutre.
"""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import get_settings
from bot.handlers._common import launch_job
from bot.models.enums import MediaScope
from bot.services.queue import JobQueue
from bot.utils.logging_config import get_logger
from bot.utils.validators import parse_handle, parse_profile

router = Router(name="commands")
log = get_logger("handlers.commands")


def _parse_args(command: CommandObject | None, reply_text: str | None):
    """Extrait (profil, limite) depuis les arguments ou le message répondu."""
    limit = 0
    raw = (command.args if command and command.args else "") or ""
    tokens = raw.split()

    # Cherche une éventuelle limite numérique parmi les tokens.
    remaining = []
    for tok in tokens:
        if tok.isdigit():
            limit = int(tok)
        else:
            remaining.append(tok)

    candidate = " ".join(remaining) if remaining else (reply_text or "")
    # On tente d'abord une URL stricte, puis un handle « nu » en repli.
    profile = parse_profile(candidate) or parse_handle(candidate)
    return profile, limit


@router.message(Command("allmedia"))
async def cmd_allmedia(
    message: Message,
    command: CommandObject,
    bot: Bot,
    job_queue: JobQueue,
) -> None:
    settings = get_settings()
    reply_text = message.reply_to_message.text if message.reply_to_message else None
    profile, limit = _parse_args(command, reply_text)

    if profile is None:
        await message.answer(
            "Indique un profil : <code>/allmedia https://x.com/username</code>\n"
            "Tu peux aussi préciser un nombre : "
            "<code>/allmedia https://x.com/username 100</code>"
        )
        return

    log.info("allmedia.requested", username=profile.username, limit=limit)
    await launch_job(
        bot=bot,
        job_queue=job_queue,
        profile=profile,
        scope=MediaScope.ALL,
        limit=limit if limit > 0 else settings.hard_media_cap,
        requested_by=message.from_user.id if message.from_user else 0,
        origin_chat_id=message.chat.id,
        ack_message=message,
    )
