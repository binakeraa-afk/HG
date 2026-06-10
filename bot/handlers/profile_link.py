"""
Handler de détection de lien de profil X.

Dès qu'un message contient un lien X/Twitter exploitable :
  - on confirme le profil détecté,
  - on propose un clavier de choix (quantité + périmètre).

Le lancement effectif se fait dans le handler de callback (callbacks.py).
"""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from bot.handlers.keyboards import choice_keyboard
from bot.utils.logging_config import get_logger
from bot.utils.validators import parse_profile

router = Router(name="profile_link")
log = get_logger("handlers.profile_link")


def _looks_like_x_link(message: Message) -> bool:
    """Filtre : le message contient-il un profil X exploitable ?"""
    return parse_profile(message.text or message.caption) is not None


@router.message(_looks_like_x_link)
async def on_profile_link(message: Message) -> None:
    profile = parse_profile(message.text or message.caption)
    if profile is None:  # garde-fou (le filtre l'a déjà validé)
        return

    log.info("link.detected", username=profile.username, chat_id=message.chat.id)
    try:
        await message.answer(
            f"🔎 Profil détecté : <b>@{profile.username}</b>\n"
            f"Que veux-tu récupérer ?",
            reply_markup=choice_keyboard(profile.username),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("link.reply_failed", error=repr(exc))
