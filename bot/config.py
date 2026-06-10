"""
Configuration centralisée et typée du bot.

Toutes les options proviennent de variables d'environnement (12-factor app).
On utilise pydantic-settings : chaque variable est validée au démarrage, ce qui
permet d'échouer immédiatement et bruyamment AU LANCEMENT plutôt que silencieusement
en cours d'exécution. C'est la seule erreur que l'on veut « visible » : une mauvaise
configuration de l'opérateur, jamais une erreur destinée à l'utilisateur final.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Schéma complet de configuration, alimenté par l'environnement."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # on ignore les variables inconnues (Railway en ajoute)
        case_sensitive=False,
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    bot_token: str = Field(..., alias="BOT_TOKEN")
    # Supergroupe (forum) dans lequel les topics seront créés.
    # Doit être un id négatif type -100xxxxxxxxxx, et le forum doit être activé.
    target_chat_id: int = Field(..., alias="TARGET_CHAT_ID")
    # Liste blanche d'utilisateurs autorisés à piloter le bot (séparés par des virgules).
    # Vide => tout le monde est autorisé (déconseillé en prod).
    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")

    # ── Base de données ───────────────────────────────────────────────────────
    # Par défaut SQLite local ; sur Railway on injecte DATABASE_URL Postgres.
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db", alias="DATABASE_URL"
    )

    # ── Téléchargement / médias ──────────────────────────────────────────────
    # Quantité par défaut de médias récupérés quand l'utilisateur ne précise rien.
    default_media_limit: int = Field(default=50, alias="DEFAULT_MEDIA_LIMIT")
    # Garde-fou absolu : on ne dépasse jamais cette valeur même pour « tout ».
    hard_media_cap: int = Field(default=2000, alias="HARD_MEDIA_CAP")
    # Répertoire de travail pour les fichiers temporaires.
    work_dir: Path = Field(default=Path("./data/downloads"), alias="WORK_DIR")
    # Taille max d'un fichier envoyable par l'API bot (50 Mo en HTTP standard).
    # Au-delà, on tente quand même mais on log et on bascule en document si besoin.
    max_upload_bytes: int = Field(default=49 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")

    # ── Concurrence / files d'attente ────────────────────────────────────────
    # Nombre de jobs (profils) traités en parallèle.
    worker_concurrency: int = Field(default=3, alias="WORKER_CONCURRENCY")
    # Nombre de téléchargements simultanés à l'intérieur d'un même job.
    download_concurrency: int = Field(default=2, alias="DOWNLOAD_CONCURRENCY")

    # ── Anti-détection / robustesse réseau ───────────────────────────────────
    # Fichier de cookies Netscape pour X (obligatoire pour la plupart des timelines).
    x_cookies_file: Path | None = Field(default=None, alias="X_COOKIES_FILE")
    # Alternative « 100 % cloud » : on colle directement le CONTENU du fichier de
    # cookies dans une variable d'environnement Railway. Le bot l'écrit sur disque
    # au démarrage. Évite tout fichier à gérer en local.
    x_cookies_content: str | None = Field(default=None, alias="X_COOKIES_CONTENT")
    # Liste de proxys (séparés par des virgules), ex: http://user:pass@ip:port
    proxies: str = Field(default="", alias="PROXIES")
    # Délai aléatoire (secondes) injecté entre deux requêtes X pour lisser la charge.
    min_request_delay: float = Field(default=1.5, alias="MIN_REQUEST_DELAY")
    max_request_delay: float = Field(default=4.0, alias="MAX_REQUEST_DELAY")

    # ── Retry ────────────────────────────────────────────────────────────────
    max_retries: int = Field(default=5, alias="MAX_RETRIES")
    retry_base_delay: float = Field(default=2.0, alias="RETRY_BASE_DELAY")
    retry_max_delay: float = Field(default=120.0, alias="RETRY_MAX_DELAY")

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    log_json: bool = Field(default=True, alias="LOG_JSON")

    # ── Validateurs ──────────────────────────────────────────────────────────
    @field_validator("work_dir")
    @classmethod
    def _ensure_work_dir(cls, v: Path) -> Path:
        """Crée le répertoire de travail au démarrage s'il n'existe pas."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    # ── Helpers dérivés ──────────────────────────────────────────────────────
    @property
    def admin_ids(self) -> set[int]:
        """Renvoie l'ensemble des ids admin sous forme typée."""
        out: set[int] = set()
        for chunk in self.admin_user_ids.split(","):
            chunk = chunk.strip()
            if chunk.isdigit() or (chunk.startswith("-") and chunk[1:].isdigit()):
                out.add(int(chunk))
        return out

    @property
    def proxy_list(self) -> list[str]:
        """Liste de proxys nettoyée."""
        return [p.strip() for p in self.proxies.split(",") if p.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    def cookies_file_path(self) -> str | None:
        """Renvoie le chemin du fichier cookies à utiliser, ou None.

        Priorité :
          1. X_COOKIES_FILE s'il pointe vers un fichier existant.
          2. X_COOKIES_CONTENT : on matérialise le contenu dans un fichier (une
             seule fois) sous le répertoire de travail. C'est le mode « cloud only ».
        Ne lève jamais : en cas de souci d'écriture, renvoie None.
        """
        if self.x_cookies_file and self.x_cookies_file.exists():
            return str(self.x_cookies_file)
        if self.x_cookies_content:
            target = self.work_dir / "x_cookies.txt"
            try:
                if not target.exists():
                    target.write_text(self.x_cookies_content, encoding="utf-8")
                return str(target)
            except Exception:
                return None
        return None


@lru_cache
def get_settings() -> Settings:
    """
    Singleton de configuration.

    lru_cache garantit qu'on ne parse l'environnement qu'une seule fois et qu'on
    réutilise la même instance partout (cohérence + perf).
    """
    return Settings()  # type: ignore[call-arg]
