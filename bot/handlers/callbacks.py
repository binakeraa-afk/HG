"""
Handler des callbacks de choix (clavier inline) : lance le job choisi.
"""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import CallbackQuery

from bot.handlers._common import launch_job
from bot.handlers.keyboards import DownloadCB
from bot.models.enums import MediaScope
from bot.services.queue import JobQueue
from bot.utils.logging_config import get_logger
from bot.utils.validators import ProfileRef

router = Router(name="callbacks")
log = get_logger("handlers.callbacks")


@router.callback_query(DownloadCB.filter())
async def on_download_choice(
    callback: CallbackQuery,
    callback_data: DownloadCB,
    bot: Bot,
    job_queue: JobQueue,
) -> None:
    """Traite le clic utilisateur et lance le job correspondant."""
    # Acquittement immédiat pour faire disparaître le spinner Telegram.
    try:
        await callback.answer("C'est parti ! 🚀")
    except Exception:  # noqa: BLE001
        pass

    try:
        scope = MediaScope(callback_data.scope)
    except ValueError:
        scope = MediaScope.VIDEOS

    profile = ProfileRef(
        username=callback_data.username,
        canonical_url=f"https://x.com/{callback_data.username}",
    )

    # On retire le clavier pour éviter les doubles clics.
    try:
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    origin_chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    await launch_job(
        bot=bot,
        job_queue=job_queue,
        profile=profile,
        scope=scope,
        limit=callback_data.limit,
        requested_by=callback.from_user.id,
        origin_chat_id=origin_chat_id,
        ack_message=callback.message,
    )
