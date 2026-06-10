"""
Claviers inline et données de callback.

On encode le choix de l'utilisateur (périmètre + quantité + username) dans le
callback_data via aiogram `CallbackData`, ce qui évite tout état serveur fragile.
"""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models.enums import MediaScope


class DownloadCB(CallbackData, prefix="dl"):
    """Donnée de callback pour lancer un téléchargement.

    scope : 'videos' ou 'all'
    limit : nombre de médias (0 = toutes, plafonné par HARD_MEDIA_CAP)
    username : handle X (≤ 15 caractères, tient dans la limite des 64 octets)
    """

    scope: str
    limit: int
    username: str


def choice_keyboard(username: str):
    """Clavier proposant les quantités et le périmètre pour un profil donné."""
    kb = InlineKeyboardBuilder()
    # Ligne 1 — vidéos par quantité.
    for n in (20, 50, 100):
        kb.button(
            text=f"🎬 {n} vidéos",
            callback_data=DownloadCB(scope=MediaScope.VIDEOS.value, limit=n, username=username),
        )
    # Ligne 2 — toutes les vidéos + tous médias.
    kb.button(
        text="🎬 Toutes les vidéos",
        callback_data=DownloadCB(scope=MediaScope.VIDEOS.value, limit=0, username=username),
    )
    kb.button(
        text="📦 Tous les médias",
        callback_data=DownloadCB(scope=MediaScope.ALL.value, limit=0, username=username),
    )
    kb.adjust(3, 2)
    return kb.as_markup()
