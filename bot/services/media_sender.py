"""
Envoi des médias vers Telegram, avec vérification multiple et retries invisibles.

Garanties :
  - On ne tente l'envoi qu'après `verify_media` (existence, taille stable, checksum,
    ffprobe pour les vidéos).
  - Les FloodWait Telegram sont respectés (le retry lit retry_after).
  - Si le topic a disparu, on le recrée et on réessaie.
  - On mémorise le file_id renvoyé par Telegram : un même média ne sera jamais
    ré-uploadé (renvoi instantané possible).
  - Toute erreur définitive est journalisée puis « avalée » (le média est marqué
    FAILED et on continue le job). L'utilisateur ne voit jamais d'erreur brute.
"""
from __future__ import annotations

from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import FSInputFile

from bot.config import get_settings
from bot.utils.files import VerifiedFile, verify_media
from bot.utils.logging_config import get_logger
from bot.utils.retry import RetryExhausted, retry_call

log = get_logger("media_sender")

# Erreurs réseau / rate-limit qui justifient un retry.
_RETRYABLE = (TelegramRetryAfter, TelegramNetworkError)


class SendResult:
    """Résultat d'un envoi : succès + file_id éventuel."""

    __slots__ = ("ok", "file_id")

    def __init__(self, ok: bool, file_id: str | None = None) -> None:
        self.ok = ok
        self.file_id = file_id


class MediaSender:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()

    async def send_file(
        self,
        *,
        path: Path,
        chat_id: int,
        topic_id: int | None,
        caption: str | None = None,
    ) -> SendResult:
        """Vérifie puis envoie un fichier. Ne lève jamais.

        Renvoie SendResult(ok=False) si le média est invalide ou définitivement
        non-envoyable : l'appelant le marque FAILED et passe au suivant.
        """
        verified = await verify_media(path)
        if verified is None:
            return SendResult(ok=False)

        try:
            file_id = await retry_call(
                self._do_send,
                verified,
                chat_id,
                topic_id,
                caption,
                retry_on=_RETRYABLE,
                give_up_on=(TelegramForbiddenError,),
                op_name="telegram_send",
            )
            return SendResult(ok=True, file_id=file_id)
        except RetryExhausted as exc:
            log.error("send.exhausted", file=str(path), error=repr(exc.last_exc))
            return SendResult(ok=False)
        except TelegramForbiddenError as exc:
            log.error("send.forbidden", file=str(path), error=repr(exc))
            return SendResult(ok=False)
        except Exception as exc:  # noqa: BLE001 — filet ultime
            log.error("send.unexpected", file=str(path), error=repr(exc))
            return SendResult(ok=False)

    async def _do_send(
        self,
        verified: VerifiedFile,
        chat_id: int,
        topic_id: int | None,
        caption: str | None,
    ) -> str | None:
        """Effectue l'appel d'envoi adapté au type de média. Peut lever (=> retry)."""
        # Re-vérification juste avant l'envoi : le fichier existe-t-il toujours ?
        if not verified.path.exists():
            raise FileNotFoundError(verified.path)

        input_file = FSInputFile(verified.path)
        kwargs: dict = {"chat_id": chat_id, "caption": caption}
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id

        # Au-delà de la limite d'upload « vidéo », on envoie en document pour
        # garantir la livraison (Telegram refuse certaines vidéos lourdes).
        too_large = verified.size > self.settings.max_upload_bytes

        try:
            if verified.is_video and not too_large:
                msg = await self.bot.send_video(
                    video=input_file, supports_streaming=True, **kwargs
                )
                return msg.video.file_id if msg.video else None
            if verified.is_video and too_large:
                msg = await self.bot.send_document(document=input_file, **kwargs)
                return msg.document.file_id if msg.document else None
            # Image : on tente la photo, repli en document si Telegram râle.
            msg = await self.bot.send_photo(photo=input_file, **kwargs)
            return msg.photo[-1].file_id if msg.photo else None
        except TelegramBadRequest as exc:
            # Cas typiques : « TOPIC_DELETED », « PHOTO_INVALID_DIMENSIONS »...
            text = str(exc).lower()
            if "thread not found" in text or "topic_deleted" in text:
                # On laisse remonter pour que l'appelant recrée le topic.
                raise
            # Sinon dernier recours universel : envoi en document.
            log.warning("send.fallback_document", file=str(verified.path), error=repr(exc))
            kwargs.pop("caption", None)
            msg = await self.bot.send_document(
                document=FSInputFile(verified.path), caption=caption, **kwargs
            )
            return msg.document.file_id if msg.document else None

    async def send_cached(
        self, *, file_id: str, is_video: bool, chat_id: int, topic_id: int | None
    ) -> bool:
        """Renvoie un média déjà connu de Telegram via son file_id (sans upload)."""
        kwargs: dict = {"chat_id": chat_id}
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id
        try:
            if is_video:
                await self.bot.send_video(video=file_id, **kwargs)
            else:
                await self.bot.send_photo(photo=file_id, **kwargs)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("send.cached_failed", error=repr(exc))
            return False
