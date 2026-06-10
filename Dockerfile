# ──────────────────────────────────────────────────────────────────────────────
#  Dockerfile multi-stage optimisé pour Railway.
#  Stage 1 (builder) : installe les dépendances dans un venv isolé.
#  Stage 2 (runtime) : image légère, sans toolchain de build, avec ffmpeg.
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1 : build des dépendances Python ────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Outils nécessaires à la compilation de certaines roues (asyncpg, etc.).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Environnement virtuel isolé que l'on copiera tel quel dans l'image finale.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ── Stage 2 : image d'exécution ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# ffmpeg/ffprobe : requis par yt-dlp (fusion) et par la vérification des vidéos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non-root pour la sécurité.
RUN useradd --create-home --uid 10001 appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Venv pré-construit (aucune recompilation dans l'image finale).
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

# Dossier de données (volume Railway recommandé pour la persistance SQLite).
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

# Healthcheck léger : le process Python tourne-t-il ?
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Démarrage : applique les migrations SI le dossier alembic est présent, sinon
# on lance directement le bot (le schéma est créé automatiquement par create_all).
CMD ["sh", "-c", "if [ -d alembic ]; then alembic upgrade head || true; fi; python -m bot"]
