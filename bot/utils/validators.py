"""
Validation et normalisation des liens X / Twitter.

On accepte :
  - https://x.com/<user>
  - https://twitter.com/<user>
  - https://www.x.com/<user>/  (avec ou sans slash final, query string, etc.)
  - liens vers un tweet précis (on en extrait le username)

On rejette tout ce qui n'est pas un profil exploitable (chemins réservés type
/home, /search, /i/...). La fonction ne lève jamais : elle renvoie None en cas
d'échec, ce qui se traduit pour l'utilisateur par un message neutre.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Segments réservés par X qui ne sont pas des noms d'utilisateur.
_RESERVED = {
    "home", "search", "explore", "notifications", "messages", "settings",
    "i", "intent", "share", "hashtag", "compose", "login", "signup",
    "tos", "privacy", "about", "download",
}

# Un handle X valide : 1 à 15 caractères alphanumériques + underscore.
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")

# Détection rapide d'une URL X/Twitter dans un texte libre.
_URL_IN_TEXT_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter|fxtwitter|vxtwitter|fixupx)\.com/\S+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProfileRef:
    """Référence normalisée vers un profil X."""

    username: str            # sans @, casse d'origine préservée
    canonical_url: str       # https://x.com/<username>

    @property
    def media_url(self) -> str:
        """URL de la timeline « médias » du profil (utilisée par yt-dlp)."""
        return f"https://x.com/{self.username}/media"


def find_x_url(text: str | None) -> str | None:
    """Extrait la première URL X/Twitter d'un texte libre, sinon None."""
    if not text:
        return None
    m = _URL_IN_TEXT_RE.search(text)
    return m.group(0) if m else None


def parse_profile(url_or_text: str | None) -> ProfileRef | None:
    """Transforme une URL (ou un texte la contenant) en ProfileRef normalisée.

    Renvoie None si rien d'exploitable n'est trouvé. Ne lève jamais.
    """
    if not url_or_text:
        return None

    # On tolère qu'on nous passe un texte entier : on isole l'URL.
    url = find_x_url(url_or_text) or url_or_text.strip()

    # Ajoute un schéma si l'utilisateur a collé « x.com/user ».
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host not in {"x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com"}:
        return None

    # Premier segment du chemin = handle potentiel.
    segments = [s for s in (parsed.path or "").split("/") if s]
    if not segments:
        return None

    handle = segments[0].lstrip("@")
    if handle.lower() in _RESERVED or not _HANDLE_RE.match(handle):
        return None

    return ProfileRef(username=handle, canonical_url=f"https://x.com/{handle}")


def parse_handle(text: str | None) -> ProfileRef | None:
    """Accepte un handle « nu » (@username ou username) sans URL.

    Utilisé en repli par la commande /allmedia. Plus permissif que parse_profile,
    donc à n'employer que dans un contexte de commande explicite (jamais en
    détection automatique, sous peine de faux positifs).
    """
    if not text:
        return None
    handle = text.strip().lstrip("@")
    if handle.lower() in _RESERVED or not _HANDLE_RE.match(handle):
        return None
    return ProfileRef(username=handle, canonical_url=f"https://x.com/{handle}")
