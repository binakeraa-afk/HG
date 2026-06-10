"""
Handler d'erreurs global (filet de sécurité ultime d'aiogram).

Toute exception non capturée dans un handler atterrit ici. On la journalise en
détail (côté serveur) et on tente, si possible, de rassurer l'utilisateur avec un
message neutre. JAMAIS de stacktrace ni de message technique exposé.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.types import ErrorEvent

from bot.utils.logging_config import get_logger

router = Router(name="errors")
log = get_logger("handlers.errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    """Capture globale. Renvoie True => l'erreur est considérée comme gérée."""
    update = event.update
    exc = event.exception
    log.error(
        "handler.exception",
        error=repr(exc),
        update_id=getattr(update, "update_id", None),
        exc_info=True,
    )

    # Tentative best-effort de répondre à l'utilisateur sans rien révéler.
    try:
        message = getattr(update, "message", None) or getattr(
            getattr(update, "callback_query", None), "message", None
        )
        if message is not None:
            await message.answer(
                "⏳ Petit souci temporaire de mon côté, je réessaie tout seul. "
                "Les médias arriveront dans le groupe."
            )
    except Exception:  # noqa: BLE001 — on n'aggrave jamais une erreur d'erreur
        pass

    return True  # erreur « avalée » : rien ne fuit
