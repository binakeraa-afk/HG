"""Énumérations partagées (statuts de jobs et de médias)."""
from __future__ import annotations

import enum


class JobStatus(str, enum.Enum):
    """Cycle de vie d'un job de récupération de profil."""

    PENDING = "pending"          # créé, en attente de prise en charge par un worker
    RESOLVING = "resolving"      # résolution du profil / listing des médias
    DOWNLOADING = "downloading"  # téléchargement des fichiers
    SENDING = "sending"          # envoi des médias vers Telegram
    COMPLETED = "completed"      # terminé avec succès
    FAILED = "failed"            # échec définitif (après tous les retries)
    CANCELLED = "cancelled"      # annulé par un admin


class MediaKind(str, enum.Enum):
    VIDEO = "video"
    PHOTO = "photo"


class MediaStatus(str, enum.Enum):
    PENDING = "pending"        # connu mais pas encore traité
    DOWNLOADED = "downloaded"  # téléchargé et vérifié localement
    SENT = "sent"              # envoyé avec succès dans le topic
    FAILED = "failed"          # impossible à récupérer/envoyer (sauté silencieusement)


class MediaScope(str, enum.Enum):
    """Périmètre demandé pour un job."""

    VIDEOS = "videos"   # uniquement les vidéos (lien de profil)
    ALL = "all"         # photos + vidéos (/allmedia)
