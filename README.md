# 🤖 X Media Bot — Bot Telegram de récupération de médias X/Twitter

Bot Telegram asynchrone, robuste et scalable. Tu envoies un lien de profil X, il
crée un **topic** dédié dans ton supergroupe, télécharge les **vidéos** (ou **tous
les médias** avec `/allmedia`) et les publie un par un — avec retries invisibles,
vérification des fichiers, reprise après redémarrage et anti rate-limit.

> ✅ **Déploiement 100 % cloud : GitHub + Railway. Rien à installer ni à exécuter
> sur ton PC.**

---

## ✨ Fonctionnalités

- 🔗 **Détection de profil X** : colle `https://x.com/username` → choix
  *20 / 50 / 100 / toutes* vidéos, ou *tous les médias*.
- 🧵 **Topics automatiques** : un topic par profil dans le supergroupe forum.
- 📦 **`/allmedia`** : photos **+** vidéos, avec barre de progression.
- 🛡️ **Robustesse extrême** : try/except partout, retries (backoff exponentiel +
  jitter, 5 tentatives), respect des *FloodWait* Telegram et des blocages X.
- 🔎 **Vérification multiple avant envoi** : taille stable, checksum SHA-256,
  contrôle `ffprobe` des vidéos.
- 💾 **Reprise après redémarrage** : l'état vit en base (SQLite/PostgreSQL), les
  jobs non terminés sont relancés au boot. Idempotence : aucun média envoyé deux fois.
- ⚡ **Parallélisme** : plusieurs profils traités simultanément, sans interférence.
- 🕵️ **Anti-détection** : rotation d'User-Agents, pool de proxys, délais « humains »,
  cookies de session.
- 🧹 **Nettoyage auto** des fichiers temporaires après envoi.
- 📝 **Logs structurés JSON** côté serveur — **jamais** d'erreur technique exposée
  à l'utilisateur.

---

## 🗂️ Arborescence

```
x-media-bot/
├── bot/
│   ├── __init__.py
│   ├── __main__.py              # Point d'entrée (python -m bot)
│   ├── config.py                # Configuration typée (pydantic-settings)
│   ├── loader.py                # Fabriques Bot / Dispatcher
│   ├── handlers/                # Couche Telegram
│   │   ├── __init__.py          #   → branche routeurs + middlewares
│   │   ├── _common.py           #   → launch_job (création + mise en file)
│   │   ├── start.py             #   → /start, /help
│   │   ├── profile_link.py      #   → détection de lien X
│   │   ├── callbacks.py         #   → clics sur le clavier inline
│   │   ├── commands.py          #   → /allmedia
│   │   ├── keyboards.py         #   → claviers + CallbackData
│   │   └── errors.py            #   → handler d'erreurs global (filet ultime)
│   ├── middlewares/
│   │   ├── __init__.py
│   │   ├── access.py            #   → liste blanche d'admins
│   │   └── throttling.py        #   → anti-spam par utilisateur
│   ├── services/                # Logique métier
│   │   ├── __init__.py
│   │   ├── extractor.py         #   → backends yt-dlp / gallery-dl
│   │   ├── topic_manager.py     #   → création/réutilisation des topics
│   │   ├── media_sender.py      #   → envoi + vérification + retries
│   │   ├── progress.py          #   → barre de progression (éditions throttlées)
│   │   ├── job_processor.py     #   → orchestration d'un job de bout en bout
│   │   └── queue.py             #   → file d'attente + pool de workers
│   ├── models/                  # ORM SQLAlchemy 2.0
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── enums.py
│   │   ├── profile.py
│   │   ├── job.py
│   │   └── media.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py            #   → moteur async + sessions
│   │   └── repository.py        #   → CRUD défensif
│   └── utils/
│       ├── __init__.py
│       ├── logging_config.py    #   → structlog
│       ├── retry.py             #   → backoff exponentiel + jitter
│       ├── files.py             #   → vérif checksum/ffprobe + nettoyage
│       ├── validators.py        #   → parsing d'URL/handle X
│       └── antidetect.py        #   → UA / proxys / délais / cookies
├── alembic/                     # Migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_initial_schema.py
├── alembic.ini
├── requirements.txt
├── Dockerfile                   # Multi-stage, ffmpeg inclus
├── railway.json                 # Config de déploiement Railway
├── .env.example                 # Modèle de variables d'environnement
├── .dockerignore
├── .gitignore
└── README.md
```

---

## 🚀 Déploiement (GitHub + Railway uniquement)

### Étape 0 — Préparer Telegram (dans l'app, sans terminal)

1. **Créer le bot** : parle à [@BotFather](https://t.me/BotFather) → `/newbot` →
   récupère le **`BOT_TOKEN`**.
2. **Créer le supergroupe** cible, puis **Paramètres → activer “Topics/Sujets”**.
3. **Ajoute ton bot** dans le groupe **en administrateur** avec le droit
   **« Gérer les sujets »** (et envoi de médias).
4. **Récupère l'ID du groupe** : ajoute temporairement
   [@username_to_id_bot](https://t.me/username_to_id_bot) (ou similaire) au groupe,
   il te donne un id du type `-100xxxxxxxxxx` → c'est **`TARGET_CHAT_ID`**.
5. **Ton user-id** : demande-le à [@userinfobot](https://t.me/userinfobot) →
   **`ADMIN_USER_IDS`**.

### Étape 1 — Mettre le code sur GitHub (glisser-déposer, sans git)

1. Va sur [github.com/new](https://github.com/new) → crée un dépôt **privé**
   (ex. `x-media-bot`).
2. Sur la page du dépôt vide : **« uploading an existing file »**.
3. Ouvre le dossier `C:\Users\PC\Claude\x-media-bot` et **glisse-dépose tout le
   contenu** (dossiers `bot/`, `alembic/`, et les fichiers `Dockerfile`,
   `railway.json`, `requirements.txt`, etc.) dans la zone d'upload GitHub.
4. **Commit** directement sur `main`.

> ⚠️ N'uploade **jamais** ton `.env` réel (il est déjà ignoré). Les secrets vont
> dans Railway, pas dans GitHub.

### Étape 2 — Déployer sur Railway

1. Va sur [railway.app](https://railway.app) → **New Project** →
   **Deploy from GitHub repo** → choisis `x-media-bot`.
2. Railway détecte le **Dockerfile** et lance le build automatiquement.
3. (Recommandé) **Base de données** : **New → Database → PostgreSQL**. Railway crée
   une variable `DATABASE_URL`. ⚠️ Remplace le préfixe `postgresql://` par
   **`postgresql+asyncpg://`** dans la variable du service bot (voir ci-dessous).
   *Sans Postgres, SQLite fonctionne — ajoute alors un **Volume** monté sur `/app/data`
   pour la persistance (sinon la base est perdue à chaque redéploiement).*

### Étape 3 — Variables d'environnement (onglet **Variables** du service)

| Variable | Obligatoire | Exemple / Valeur |
|---|---|---|
| `BOT_TOKEN` | ✅ | `123456:ABC-DEF...` |
| `TARGET_CHAT_ID` | ✅ | `-1001234567890` |
| `ADMIN_USER_IDS` | recommandé | `11111111,22222222` |
| `DATABASE_URL` | si Postgres | `postgresql+asyncpg://user:pass@host:5432/db` |
| `X_COOKIES_CONTENT` | ✅ pour X | *(colle le contenu de `cookies.txt`)* |
| `PROXIES` | optionnel | `http://user:pass@ip:port,http://ip2:port` |
| `DEFAULT_MEDIA_LIMIT` | non | `50` |
| `HARD_MEDIA_CAP` | non | `2000` |
| `WORKER_CONCURRENCY` | non | `3` |
| `MAX_RETRIES` | non | `5` |
| `LOG_JSON` | non | `true` |

> La liste complète et commentée est dans **`.env.example`**.

### Étape 4 — Cookies X sans fichier local (mode « cloud »)

X exige généralement une session connectée pour lister les médias d'un profil.

1. Dans **ton navigateur** (connecté à X), installe une extension
   **« Get cookies.txt »** (format **Netscape**).
2. Sur `x.com`, **exporte les cookies** → tu obtiens un texte.
3. Copie **tout** ce texte et colle-le dans la variable Railway **`X_COOKIES_CONTENT`**
   (champ multiligne). Le bot écrit le fichier lui-même au démarrage.

*(Aucun fichier à gérer sur ton PC : seul le presse-papier est utilisé.)*

### Étape 5 — Lancer & vérifier

- Railway redéploie à chaque **push GitHub**. Le conteneur exécute
  `alembic upgrade head` puis `python -m bot`.
- Ouvre les **Logs** Railway : tu dois voir `boot.ready`.
- Dans Telegram, envoie `/start` à ton bot, puis un lien `https://x.com/...`.

---

## 🕹️ Utilisation

| Action | Effet |
|---|---|
| Envoyer `https://x.com/username` | Propose 20 / 50 / 100 / toutes vidéos, ou tous médias |
| `/allmedia https://x.com/username` | Tous les médias (photos + vidéos) |
| `/allmedia https://x.com/username 100` | Les 100 derniers médias |
| `/allmedia @username` | Handle « nu » accepté |
| `/start`, `/help` | Aide |

Chaque profil obtient son **topic** dans le supergroupe ; les médias y sont publiés
un par un avec une barre de progression mise à jour en temps réel.

---

## 🛡️ Robustesse & anti-blocage (résumé technique)

- **Retries** : `bot/utils/retry.py` — backoff exponentiel plafonné + *full jitter*,
  respect de `retry_after` (FloodWait Telegram, `Retry-After` HTTP).
- **Vérification fichiers** : `bot/utils/files.py` — taille stable, SHA-256, `ffprobe`.
- **Erreurs invisibles** : try/except systématique + handler d'erreurs global
  (`bot/handlers/errors.py`). L'utilisateur ne voit que des messages neutres.
- **Reprise** : jobs et médias persistés (`bot/models/`), requeue au démarrage
  (`bot/services/queue.py:requeue_pending`), dédup par clé stable.
- **Anti-détection** : `bot/utils/antidetect.py` — UA aléatoires, pool de proxys
  avec quarantaine, délais aléatoires entre requêtes, cookies de session.
- **Parallélisme isolé** : un dossier de travail, un topic et des lignes en base
  par job.

---

## ⚖️ Cadre d'usage

Cet outil est destiné à récupérer des **médias publics** de profils que tu as le
droit de consulter, pour un usage personnel/archivage. Respecte les
**conditions d'utilisation de X**, le **droit d'auteur** et la **vie privée** des
personnes concernées. Tu es responsable de l'utilisation que tu en fais.

---

## 🧩 Dépannage rapide

| Symptôme | Piste |
|---|---|
| Le bot ne crée pas de topic | Bot admin + droit « Gérer les sujets » ? Topics activés ? `TARGET_CHAT_ID` correct (`-100…`) ? |
| Aucune vidéo récupérée | `X_COOKIES_CONTENT` manquant/expiré → réexporte les cookies |
| Base perdue au redéploiement (SQLite) | Ajoute un **Volume** Railway sur `/app/data`, ou passe à PostgreSQL |
| `DATABASE_URL` Postgres ne marche pas | Préfixe `postgresql+asyncpg://` (pas `postgres://`) |
| Rate-limit fréquent | Baisse `WORKER_CONCURRENCY`, augmente `MIN/MAX_REQUEST_DELAY`, ajoute des `PROXIES` |
```
