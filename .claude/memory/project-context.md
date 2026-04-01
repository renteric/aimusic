# Project Context Memory

## What this project is

A self-hosted audio downloader. Users visit the web UI, paste a URL or type
search terms, and the app downloads audio files (MP3, FLAC, etc.) via yt-dlp.
Files are stored in a `media/` directory on the host, browseable via the UI.
Multiple user accounts with role-based access are supported.

## Key design decisions

- **No spotdl** — was removed in favour of yt-dlp which covers all required
  sources (YouTube, SoundCloud, etc.) without extra auth complexity.
- **Uvicorn in Docker** — FastAPI dev server is only used for local development.
  The container uses Uvicorn with 1 worker (single worker required for in-memory
  SSE job tracking).
- **SSE for verbose logs** — verbose download mode streams yt-dlp output to the
  browser via Server-Sent Events. nginx must have `proxy_buffering off` for the
  `/api/download/logs/` path.
- **Subprocess-based downloads** — Flask spawns `downloader_cli.py` as a
  subprocess so long downloads do not block the web worker thread.
- **In-memory job registry** — `JOBS: dict[str, DownloadJob]` tracks in-flight
  jobs. Cleaned up after `JOB_MAX_AGE_SECONDS`. Acceptable for a single-user
  tool; would need Redis for multi-instance deployment.
- **RBAC** — four roles (`superadmin`, `admin`, `user`, `viewer`) enforced by
  `@require_role(...)` in `backend/app/core/roles.py`. The superadmin is seeded
  on first run and cannot be deleted. User management is at `/admin` (superadmin
  and admin only).

## Path layout inside Docker

```text
/app/
├── app/                ← application package (backend/app/)
│   ├── __init__.py
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── services/
│   └── utils/
├── media/              ← bind-mounted from host ./media
├── docs/               ← bind-mounted from host ./docs (My Docs markdown files)
└── data/               ← bind-mounted from host ./data (SQLite DB)
```

Working directory is `/app`. `BASE_DIR` resolves to `/app` (3 parents up from
`app/core/config.py`). `MEDIA_DIR` resolves to `/app/media`.

## Environment

- Python 3.13
- Debian slim base (`python:3.13-slim`)
- ffmpeg, exiftool, nodejs, gosu installed as system packages
- Uvicorn as ASGI server (1 worker)
- Entrypoint script (`entrypoint.sh`) chowns bind-mounted volumes before
  dropping to `appuser` via gosu

## Ports

Default: host `${APP_PORT:-80}` → nginx:80 → backend:5000.
Backend port configurable via `API_PORT` in `.env`.

## Internationalisation

vue-i18n v11 (Composition API mode, `legacy: false`). Three locales: `en` (default), `fr`, `es`.
Locale JSON files in `frontend/src/i18n/locales/`. Pre-compiled at build time by
`@intlify/unplugin-vue-i18n`; runtime-only build aliased in `vite.config.ts` — no eval() needed.
Language persisted to `localStorage` key `ai-music-locale`. **Never use ASCII apostrophe `'`
in locale strings** — use typographic `'` (U+2019); the vue-i18n compiler treats `'` as an
escape character and throws a SyntaxError at runtime.
