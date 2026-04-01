---
name: Separator service refactored to API-only
description: separator/src/api.py stripped of HTML page routes and templates; transcribe_service.py converted from Flask to FastAPI
type: project
---

The separator microservice (`separator/src/`) was refactored to be API-only.

**Why:** The Vue frontend already has full stem UI (DemucsView, LalaiView, AudioSepView, StemLibraryView). The old Jinja2 templates and vanilla-JS static files were redundant.

**Changes made:**
- Removed 6 HTML page routes (`/`, `/lalai`, `/audiosep`, `/player`, `/list`, `/browse/{folder}`) from `separator/src/api.py`
- Deleted `separator/src/templates/` and `separator/src/static/` directories
- Added `GET /api/library` and `GET /api/library/{folder}` JSON endpoints to replace the old browse pages
- Converted `backend/app/services/transcribe_service.py` from Flask to FastAPI with Pydantic request/response models (`TranscribeRequest`, `TranscribeResponse`)
- Updated `requirements.transcribe.txt`: replaced `flask` with `fastapi` + `uvicorn[standard]`
- Updated `Dockerfile.transcribe` CMD to use uvicorn
- Moved hardcoded CORS origins and TrustedHost lists into `settings.py` as `MUSEP_CORS_ORIGINS` and `MUSEP_ALLOWED_HOSTS`
- Deleted `separator/.env`, `separator/.env.example`, `separator/.env copy` (had real API key)
- Removed `env_file = ".env"` from separator `Settings.Config` — env vars now come from docker-compose root `.env`
- Expanded root `.env.example` with all `MUSEP_` separator settings and `TRANSCRIBE_PORT`

**How to apply:** The separator is internal-only (backend proxies it). Its `.env` config comes entirely from the root `.env` file via docker-compose `env_file: .env`.

---

## Rebuild review fixes (2026-03-29)

**Bug fixes made before rebuild:**

- `transcribe/src/lib/transcribe_cli.py`: removed stale `try/except` import of `app.services.constants` — replaced with direct `from constants import SUPPORTED_FORMATS` (files moved to `transcribe/src/lib/`)
- `docker-compose.yml`: whisper-cache volume was mounted to `/root/.cache/whisper` but container runs as non-root user; fixed to `/app/.cache/whisper` via `WHISPER_CACHE_DIR` env var
- `transcribe/src/lib/transcribe_service.py`: added `WHISPER_CACHE_DIR` env var support (`download_root` param on `whisper.load_model()`)
- `transcribe/Dockerfile`: creates `/app/.cache/whisper`, chowns it, sets `ENV WHISPER_CACHE_DIR=/app/.cache/whisper`
- `docker-compose.yml`: renamed `music-separator:latest` → `ai-music-separator:latest`, `music-transcribe:latest` → `ai-music-transcribe:latest`
- `backend/app/core/config.py`: removed stale `FLASK_DEBUG` env var fallback — reads `API_DEBUG` only
- `Makefile`: fixed help text "Flask" → "Uvicorn"

**Docs rewritten:**

- `CLAUDE.md`: full rewrite — correct FastAPI/Uvicorn/JWT stack, `API_*` env vars (not `FLASK_*`), accurate repo structure with `separator/` and `transcribe/`
- `README.md`: full rewrite — removed all Flask/Gunicorn references, added stem separation and transcription features, correct env var table
- `.env.example`: added `WHISPER_CACHE_DIR`, `HUGGINGFACE_HUB_API_KEY`
