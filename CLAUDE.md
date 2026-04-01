# CLAUDE.md — AI-Music

This file is read automatically by Claude Code at the start of every session.
It gives the AI assistant context about this project and how to work in it.

---

## Project Overview

**AI-Music** is a full-stack web application for downloading and managing audio from YouTube
and other sources via yt-dlp. It consists of a **FastAPI backend**, a **Vue 3 + TypeScript SPA
frontend**, and two internal microservices (stem extraction + Whisper transcription).

### Key capabilities

- Download audio (mp3/flac/wav/ogg/opus) via URL or search query
- Manage a media file library (browse, stream, delete)
- Clean audio metadata (exiftool / mutagen)
- Transcribe audio via a Whisper microservice
- Extract melody lines to MIDI
- Separate audio into stems (vocals, drums, bass, guitar, piano) via Demucs / LALAL.AI / AudioSep
- Browse, create, and edit Markdown documents (`/mydocs`) — live preview, rich-text mode, full-text search, in-doc link navigation
- Login-protected — all routes require authentication
- Role-based access control (superadmin / admin / user / viewer)
- User management admin panel (`/admin`) — full CRUD, role assignment
- Multilingual UI — English (default), Français, Español; language switcher in NavBar and login page

---

## Repository Structure

```text
aimusic/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # create_app() FastAPI factory
│   │   ├── main.py              # Uvicorn entry point
│   │   ├── api/
│   │   │   ├── admin.py         # /api/admin — user CRUD (superadmin + admin only)
│   │   │   ├── auth.py          # /api/auth — login, logout, me, change-password
│   │   │   ├── docs.py          # /api/docs — list, get, create, update, rename, delete, search
│   │   │   ├── download.py      # /api/download — start job, SSE log stream
│   │   │   ├── media.py         # /api/media — list, stream, delete, clean, transcribe
│   │   │   └── stem.py          # /api/stem — proxy to separator microservice
│   │   ├── core/
│   │   │   ├── auth.py          # JWT helpers — create_access_token, get_current_user
│   │   │   ├── config.py        # AppConfig — all settings from .env
│   │   │   ├── roles.py         # require_roles() dependency — RBAC enforcement
│   │   │   └── security.py      # SecurityHeadersMiddleware
│   │   ├── models/
│   │   │   └── user.py          # User model, init_db(), get_connection()
│   │   ├── services/
│   │   │   ├── constants.py     # SUPPORTED_FORMATS
│   │   │   ├── downloader_cli.py
│   │   │   ├── extract_melody_cli.py
│   │   │   └── metadata_cleaner.py
│   │   └── utils/
│   │       └── files.py         # safe_media_path(), safe_docs_path(), human_size()
│   ├── tests/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.ts              # App entry: createApp + Pinia + Router + i18n
│   │   ├── App.vue              # Root component (NavBar + footer outside /login)
│   │   ├── assets/css/main.css  # Custom styles on top of Bootstrap
│   │   ├── components/NavBar.vue
│   │   ├── composables/usePlayer.ts
│   │   ├── i18n/
│   │   │   ├── index.ts         # createI18n, setLocale(), getInitialLocale()
│   │   │   └── locales/
│   │   │       ├── en.json      # English translations (default)
│   │   │       ├── fr.json      # French translations
│   │   │       └── es.json      # Spanish translations
│   │   ├── router/index.ts      # Vue Router 4 — auth guard
│   │   ├── services/
│   │   │   ├── api.ts           # Axios instance + all API helpers
│   │   │   └── types.ts         # TypeScript interfaces
│   │   ├── stores/auth.ts       # Pinia auth store
│   │   └── views/
│   │       ├── LoginView.vue
│   │       ├── HomeView.vue
│   │       ├── DownloadView.vue
│   │       ├── MediaFilesView.vue
│   │       ├── AdminView.vue    # /admin — user management
│   │       ├── MyDocsView.vue   # /mydocs — Markdown editor
│   │       └── stem/            # DemucsView, LalaiView, AudioSepView, StemLibraryView, StemPlayerView
│   ├── Dockerfile               # Multi-stage: Node 22 builder → nginx 1.27
│   ├── nginx.conf
│   ├── package.json
│   └── vite.config.ts
├── separator/                   # Stem extraction microservice (internal only)
│   ├── src/
│   │   ├── api.py               # FastAPI app — REST endpoints only (no web UI)
│   │   ├── cli.py               # Click CLI with rich TUI
│   │   ├── config/settings.py   # pydantic-settings (MUSEP_ prefix)
│   │   ├── core/
│   │   │   ├── separator.py     # AudioSeparator — Demucs + open-unmix
│   │   │   ├── lalai.py         # LalaiSeparator — LALAL.AI v1 API
│   │   │   └── audiosep.py      # AudioSepSeparator — text-query model
│   │   └── lib/
│   │       ├── audio.py
│   │       └── logging.py
│   ├── Dockerfile
│   └── requirements.txt
├── transcribe/                  # Whisper transcription microservice (internal only)
│   ├── src/lib/
│   │   ├── transcribe_service.py  # FastAPI app
│   │   ├── transcribe_cli.py      # Batch CLI tool
│   │   └── constants.py
│   ├── Dockerfile
│   └── requirements.txt
├── .claude/
│   ├── memory/
│   ├── rules/
│   └── skills/
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

---

## Stack

### Backend

| Technology | Version | Purpose |
| ---------- | ------- | ------- |
| Python | 3.13 | Runtime |
| FastAPI | ≥ 0.115 | Web framework, app factory pattern |
| Uvicorn | ≥ 0.32 | ASGI server (1 worker + async) |
| python-jose | ≥ 3.3 | JWT signing / verification |
| Werkzeug | ≥ 3.1 | Password hashing (PBKDF2-SHA256) |
| httpx | ≥ 0.27 | Async HTTP client (separator proxy) |
| yt-dlp | latest | Media extraction |
| mutagen | latest | Audio tag manipulation |
| python-dotenv | latest | `.env` loading |
| SQLite | built-in | User persistence (WAL mode, foreign keys on) |

### Frontend

| Technology | Version | Purpose |
| ---------- | ------- | ------- |
| Vue 3 | ≥ 3.5 | UI framework (Composition API, `<script setup>`) |
| TypeScript | ≥ 5.7 | Type safety |
| Vite | ≥ 6.0 | Build tool + dev server |
| Pinia | ≥ 2.3 | State management |
| Vue Router 4 | ≥ 4.5 | Client-side routing (history mode) |
| vue-i18n | ≥ 11.0 | Internationalisation (EN / FR / ES) — Composition API mode, pre-compiled at build time |
| Axios | ≥ 1.7 | HTTP client (`withCredentials: true`) |
| Bootstrap 5 | ≥ 5.3 | CSS framework (npm, not CDN) |
| Bootstrap Icons | ≥ 1.11 | Icon set (npm) |
| nginx 1.27 | alpine | SPA server + `/api/` proxy |

---

## Architecture Rules

1. **Config in `.env` only.** Never hardcode ports, secrets, or paths. All runtime settings
   flow through `AppConfig` (`backend/app/core/config.py`) which reads from environment
   variables. Separator config uses pydantic-settings with the `MUSEP_` prefix.

2. **Objects for config and jobs.** Use `AppConfig` (class) for app settings,
   `DownloadConfig` (dataclass) for per-download parameters, and `DownloadJob`
   (class) for in-flight job tracking.

3. **Security first.**
   - `safe_media_path()` (`backend/app/utils/files.py`) must guard every file-serving route.
   - Never serve files outside `AppConfig.MEDIA_DIR`.
   - Only stream files with `audio/*` MIME type via `/api/media/stream/`.
   - All state-changing API endpoints accept JSON only (CSRF protection for SPA).
   - Security headers set in both FastAPI (`core/security.py` middleware) and nginx (`nginx.conf`).

4. **Role-based access control.**
   - Use `Depends(require_roles(...))` from `backend/app/core/roles.py` on every route that is not open to all authenticated users.
   - Roles in order of privilege: `superadmin` → `admin` → `user` → `viewer`.
   - The `superadmin` account (seeded on first run) cannot be deleted and its role cannot be changed via the API.
   - `viewer` role: read-only — can browse and play media but cannot delete, clean, or transcribe.
   - `user` role: full media operations but no access to `/api/admin` or the `/admin` page.
   - `admin` and `superadmin`: full access including user management.
   - The frontend mirrors all restrictions based on `auth.isAdmin` / `auth.isViewer` from the Pinia auth store.

5. **Python: class objects, reuse, constants, and optimization.**
   - **Use classes for related logic.** Group related state and behaviour into classes. Use `@dataclass` for value objects (config, params). Use plain classes with `__init__` for stateful objects. Never write a collection of bare module-level functions when a class is the right abstraction.
   - **Reuse before writing.** Before adding new code, search `backend/app/utils/`, `backend/app/core/`, and `backend/app/services/` for existing classes or functions that already do the job. Extend or call them — never duplicate.
   - **Constants in constant files.** Magic strings, numbers, and enum-like values belong in a constants file (e.g. `backend/app/services/constants.py`). Never scatter literals across modules. Import from the constants file everywhere.
   - **Optimize always.** Prefer `set`/`dict` lookups over list scans. Use generators and comprehensions. Avoid redundant DB queries. Never block the async event loop with synchronous I/O. Avoid O(n²) patterns in hot paths.
   - When editing any Python file, scan the whole file for violations of these rules and fix them in the same change.

6. **Docstrings on everything (Python).** All public classes, methods, and functions
   must have Google-style docstrings with `Args:`, `Returns:`, and `Raises:` sections.
   Module-level docstrings are required in every `.py` file. Private helpers (`_name`)
   must also have docstrings when the logic is non-obvious.

7. **Type hints required (Python).** Every function signature must be fully annotated.
   Use `X | Y` union syntax (Python 3.10+), not `Optional[X]` or `Union[X, Y]`.

8. **TypeScript throughout (frontend).** No untyped code. Define interfaces in
   `frontend/src/services/types.ts`. Use `<script setup lang="ts">` in all SFCs.

9. **Single Uvicorn worker.** The `JOBS` dict is in-memory; multiple workers each
   have their own dict which breaks SSE streams. Always run 1 worker.

10. **Internationalisation (i18n).**
    - All user-visible strings in Vue components must use `t('key')` from `useI18n()`.
    - Locale JSON files live in `frontend/src/i18n/locales/` — one file per language.
    - `@intlify/unplugin-vue-i18n` pre-compiles all locale JSON at build time. The
      runtime-only vue-i18n build is aliased in `vite.config.ts` — the message compiler
      is never bundled, keeping the bundle smaller and satisfying the strict CSP.
    - Never use ASCII apostrophes (`'`) in locale strings — they are escape characters
      in the vue-i18n message syntax. Use the typographic right single quote `'` (U+2019).
    - Language choice is persisted to `localStorage` under key `ai-powered-music-locale`.
    - Browser language is auto-detected on first visit; falls back to `en`.

---

## Code Style

### Python

- Line length: **120 characters** (matches `.flake8` and `pyproject.toml`)
- Formatter: **black** (line-length 120)
- Import sorter: **isort** (profile = black)
- Linter: **flake8**
- Python version: **3.13**
- Separator uses **88 characters** (its own pyproject.toml)

### TypeScript / Vue

- Strict TypeScript (`"strict": true` in `tsconfig.json`)
- `<script setup lang="ts">` in all Single File Components
- Composables in `src/composables/` prefixed with `use`
- API functions in `src/services/api.ts`; types in `src/services/types.ts`
- Pinia stores in `src/stores/`

---

## Docker Rules

- Backend base image: `python:3.13-slim` (not alpine, not full)
- Frontend: multi-stage build — `node:22-alpine` builder → `nginx:1.27-alpine`
- Clear APT lists in the same `RUN` layer that installs packages
- Use `--no-cache-dir` with every `pip install`
- The backend container runs as a **non-root user** via `gosu` entrypoint
- Media files are **not** baked into the image — bind-mounted volume (`./media:/app/media`)
- Docs files are **not** baked into the image — bind-mounted volume (`./docs:/app/docs`)
- `.dockerignore` excludes `.venv/`, `media/`, `docs/`, `.env`, `node_modules/`, `frontend/dist/`

---

## Environment Variables

All settings live in `.env` (copy from `.env.example`).

### Backend service

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `APP_PORT` | `80` | Host port for the nginx frontend |
| `API_HOST` | `0.0.0.0` | Uvicorn bind host |
| `API_PORT` | `5000` | Uvicorn bind port |
| `API_DEBUG` | `false` | Enable debug mode (never true in production) |
| `SECRET_KEY` | — | JWT signing key — **must be set** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT lifetime (24 h) |
| `DB_PATH` | `data/app.db` | SQLite database path |
| `ADMIN_USERNAME` | `admin` | First-run superadmin username |
| `ADMIN_PASSWORD` | — | First-run superadmin password — **must be set** |
| `MEDIA_DIR` | `media` | Output folder for downloaded files |
| `DOCS_DIR` | `docs` | Folder for My Docs markdown files |
| `JOB_MAX_AGE_SECONDS` | `3600` | How long completed job logs are kept |
| `TRANSCRIBE_SERVICE_URL` | `http://transcribe:9000` | Whisper service URL |
| `TRANSCRIBE_PORT` | `9000` | Port the transcription service binds to |
| `SEPARATOR_URL` | `http://separator:8000` | Separator microservice URL |
| `CORS_ORIGINS` | `` | Dev CORS origins (empty in production) |

### Separator (all prefixed `MUSEP_`)

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `MUSEP_API_HOST` | `0.0.0.0` | Separator bind host |
| `MUSEP_API_PORT` | `8000` | Separator bind port |
| `MUSEP_CORS_ORIGINS` | `http://localhost:8000,...` | Allowed CORS origins |
| `MUSEP_ALLOWED_HOSTS` | `localhost,127.0.0.1,...` | TrustedHost values |
| `MUSEP_MAX_UPLOAD_SIZE_MB` | `200` | Max upload size in MB |
| `MUSEP_MP3_BITRATE` | `320` | Output MP3 quality |
| `MUSEP_DEVICE` | auto | `cpu`, `cuda`, or `mps` |
| `MUSEP_LALALAI_API_KEY` | `` | LALAL.AI API key |
| `HUGGINGFACE_HUB_API_KEY` | `` | Hugging Face Hub API key (model downloads) |
| `WHISPER_CACHE_DIR` | `/app/.cache/whisper` | Whisper model weight cache |

---

## Common Tasks

### Run with Docker (recommended)

```bash
make up                 # docker compose up -d
make logs               # tail logs
make down               # stop
make rebuild            # rebuild from scratch then start
make ps                 # container health status
```

### Run locally (no Docker)

```bash
# Backend
make install-backend
make backend-dev        # Uvicorn dev server on port 5000

# Frontend (separate terminal)
make install-frontend
make frontend-dev       # Vite dev server on port 5173
```

### Run tests

```bash
make test               # pytest on backend
make lint               # flake8 on backend
```

### CLI

```bash
make download URL="https://youtu.be/xyz" FORMAT=mp3 BITRATE=320k
make clean-meta AUDIO_PATH=media/somefile.mp3 ARGS="--clean --show"
make docker-download URL="https://youtu.be/xyz"   # via Docker
```

---

## Separator Microservice

The `separator/` directory is an internal FastAPI microservice for AI-powered audio stem
extraction. It is **API-only** — no web UI. All UI is in the Vue frontend (`/views/stem/`).
The backend proxies every request to it via `GET|POST /api/stem/*`.

### Key files

| File | Role |
| ---- | ---- |
| `separator/src/api.py` | FastAPI app — all REST endpoints |
| `separator/src/cli.py` | Click CLI with rich TUI |
| `separator/src/core/separator.py` | `AudioSeparator` — Demucs + open-unmix subprocess |
| `separator/src/core/lalai.py` | `LalaiSeparator` — LALAL.AI v1 API client |
| `separator/src/core/audiosep.py` | `AudioSepSeparator` — text-query local model |
| `separator/src/config/settings.py` | All config via pydantic-settings (`MUSEP_` prefix) |

### Providers

- **Demucs / open-unmix** — local ML, runs on CPU/CUDA/MPS. Default model: `htdemucs_6s` (6 stems).
- **LALAL.AI** — cloud API, requires `MUSEP_LALALAI_API_KEY`.
- **AudioSep** — local text-query model, requires separate install + ~1 GB checkpoint.

### Configuration

All settings use the `MUSEP_` prefix and come from the **root `.env`** via `docker-compose env_file`.
There is no separate `separator/.env`. See the root `.env.example` for all `MUSEP_` variables.

### Audio processing rules

- FFmpeg must be on PATH — always available inside the container.
- Input audio is converted to 44100 Hz stereo WAV before passing to Demucs.
- Demucs runs as a **subprocess** — never via Python API.
- `htdemucs_6s` supports: `vocals, drums, bass, guitar, piano, other` only. Woodwinds/brass/flute map to `other`.
- Device priority: CUDA → MPS → CPU (auto-detected at startup).

### What NOT to do (separator)

- Do not add HTML templates, static files, or page routes — the service is intentionally API-only.
- Do not create a `separator/.env` — all config flows from the root `.env`.
- Do not increase Uvicorn workers — the in-memory `jobs` dict is not shared.

---

## What NOT to Do

- Do not add `spotdl` back as a dependency — yt-dlp covers all required sources.
- Do not store secrets in source files or commit `.env`.
- Do not serve files outside `MEDIA_DIR` — always use `safe_media_path()`.
- Do not serve docs outside `DOCS_DIR` — always use `safe_docs_path()`.
- Do not use multiple Uvicorn workers — SSE job streaming requires a single worker.
- Do not use CDN links for Bootstrap or Bootstrap Icons — use npm packages for clean CSP.
- Do not add bare ASCII apostrophes (`'`) to locale JSON files — vue-i18n's message compiler treats `'` as an escape character and will throw a SyntaxError at runtime. Use the typographic right single quote `'` (U+2019) instead.
- Do not add untyped `any` in TypeScript without justification.
- Do not protect routes with only `@login_required` — use `Depends(require_roles(...))` from `core/roles.py`.
- Do not allow deleting or changing the role of the `superadmin` account — it is protected at the API level.
- Do not add role checks only on the frontend — the backend must always enforce them independently.
- Do not hardcode ports, URLs, or credentials anywhere in source code — always use env vars via `AppConfig` or `settings`.
- Do not use `style="..."` (static) or `:style="..."` (bound to a static value) in Vue templates — add a named class to `frontend/src/assets/css/main.css` instead. The only acceptable `:style` use is for truly runtime-dynamic values (e.g. a color fetched from data). This is required for CSP compliance (`style-src 'self'`) and to avoid JS/CSS injection vectors.

---

## Project Memory

See `.claude/memory/` for persisted notes across sessions.
See `.claude/rules/` for detailed coding and Docker standards.
See `.claude/skills/` for reusable task playbooks.
