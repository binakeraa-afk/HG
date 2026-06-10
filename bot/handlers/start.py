"""Handlers d'accueil : /start et /help."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="start")

_WELCOME = (
    "👋 <b>Bot de récupération de médias X</b>\n\n"
    "Envoie-moi simplement un lien de profil :\n"
    "<code>https://x.com/nom_utilisateur</code>\n\n"
    "Je te proposerai de récupérer <b>20 / 50 / 100 / toutes</b> les vidéos, "
    "ou <b>tous les médias</b> (photos + vidéos).\n\n"
    "Chaque profil obtient son propre <b>topic</b> dans le groupe dédié, "
    "et les médias y sont publiés un par un.\n\n"
    "<b>Commandes</b>\n"
    "• <code>/allmedia &lt;lien&gt; [nombre]</code> — tous les médias d'un profil\n"
    "• <code>/help</code> — afficher cette aide"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(_WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_WELCOME)
