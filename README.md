# AI-Music

A full-stack web application for downloading and managing audio from YouTube and other
sources via [yt-dlp](https://github.com/yt-dlp/yt-dlp). Built with a **FastAPI** backend,
a **Vue 3 + TypeScript** SPA frontend, and two internal microservices for stem extraction
and transcription. Login-protected, containerised, and ready to self-host.

---

## Features

| Feature | Details |
| ------- | ------- |
| Multiple formats | MP3, FLAC, M4A, OGG, OPUS, WAV |
| Quality control | Bitrate selection from 8k up to 320k |
| Batch download | Playlist URL or multi-line text search |
| Real-time logs | Verbose mode streams yt-dlp output live via SSE |
| Auto-transcribe / auto-stem | Optionally run Whisper and/or Demucs automatically after each download |
| Download queue | Track all download jobs and their status from a dedicated queue view |
| Media browser | Sortable file listing with in-browser player, download, delete |
| Metadata cleaner | Strip all tags from files — from the UI or the CLI |
| Audio transcription | Whisper microservice — transcribes audio to Markdown beside the file |
| Melody extractor | Extract a melody line to MIDI + MusicXML from any audio file |
| Stem separation | Split audio into vocals, drums, bass, guitar, piano via Demucs / LALAL.AI / AudioSep |
| AI analysis | Clean transcripts, analyse song structure, generate tags, and translate lyrics via Claude |
| My Docs | Markdown document browser and editor with live preview, rich-text mode, rename, and full-text search |
| Storage dashboard | Media library usage breakdown by file format and folder |
| Authentication | SQLite-backed login, JWT cookies (HttpOnly + SameSite=Lax) |
| Role-based access | Four roles: superadmin, admin, user, viewer — enforced at API and UI level |
| User management | Admin panel (`/admin`) for full user CRUD — create, edit, delete, set role |
| Multilingual UI | English, Français, Español — language switcher in NavBar and login page, persisted across sessions |
| Makefile | Single entry point for all Docker and CLI operations |

---

## User Roles

| Role | Admin panel | Download | Media browse | Delete / Clean / Transcribe |
| ---- | ----------- | -------- | ------------ | --------------------------- |
| `superadmin` | Full access, can edit any account | ✓ | ✓ | ✓ |
| `admin` | Full access, cannot touch superadmin account | ✓ | ✓ | ✓ |
| `user` | No access | ✓ | ✓ | ✓ |
| `viewer` | No access | ✓ | Browse + play only | ✗ |

The first account created on startup is always `superadmin`. It cannot be deleted and its
role cannot be changed. All other accounts are managed from `/admin`.

---

## Multilingual Support

The UI ships in three languages selectable at any time from the NavBar dropdown or the login page:

| Code | Language |
| ---- | -------- |
| `en` | English (default) |
| `fr` | Français |
| `es` | Español |

The choice is persisted in `localStorage` (`ai-powered-music-locale`) and applied on every subsequent visit.
On first visit the browser's preferred language is used if supported, otherwise English.

Locale files live in `frontend/src/i18n/locales/` — one JSON file per language.
All messages are pre-compiled at build time by `@intlify/unplugin-vue-i18n`, so no runtime
eval is ever needed (compatible with the strict `Content-Security-Policy: script-src 'self'`).

To add a new language:

1. Copy `en.json` to e.g. `pt.json` and translate all values.
2. Add `'pt'` to the `SUPPORTED` array and import the file in `frontend/src/i18n/index.ts`.
3. Add the language to the `languages` array in `NavBar.vue` and `LoginView.vue`.

---

## Quick Start (Docker — recommended)

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd aimusic
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY, ADMIN_PASSWORD, and ANTHROPIC_API_KEY
```

### 3. Start the stack

```bash
make up
```

Open `http://localhost` (or the port set in `APP_PORT`) in your browser.
Log in with the admin credentials from your `.env` file.

Downloaded files land in `./media/` on the host (mounted as a volume).

### Stop / restart / rebuild

```bash
make down           # stop
make up             # start (images already built)
make rebuild        # rebuild from scratch then start
make logs           # tail container logs
make ps             # show container health status
make backend-shell  # open a shell in the backend container
make frontend-shell # open a shell in the frontend container
```

---

## Configuration (.env)

All settings live in `.env`. Copy `.env.example` to get started.

### Application

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `APP_PORT` | `80` | Host port for the nginx frontend |
| `API_HOST` | `0.0.0.0` | Uvicorn bind address |
| `API_PORT` | `5000` | Uvicorn internal port |
| `API_DEBUG` | `false` | Enable debug mode (never `true` in production) |
| `SECRET_KEY` | — | JWT signing secret — **generate and set this** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT token lifetime (24 h) |
| `DB_PATH` | `data/app.db` | SQLite database path |
| `ADMIN_USERNAME` | `admin` | Auto-created superadmin username (first run only) |
| `ADMIN_PASSWORD` | — | Auto-created superadmin password — **must be set** |
| `MEDIA_DIR` | `media` | Output folder for downloaded files |
| `DOCS_DIR` | `docs` | Folder for My Docs markdown files |
| `JOB_MAX_AGE_SECONDS` | `3600` | How long finished job logs are kept in memory |
| `TRANSCRIBE_SERVICE_URL` | `http://transcribe:9000` | Whisper service URL |
| `TRANSCRIBE_PORT` | `9000` | Port the transcription service binds to |
| `SEPARATOR_URL` | `http://separator:8000` | Stem extraction service URL |
| `ANTHROPIC_API_KEY` | — | Claude API key for AI analysis features (optional) |
| `CORS_ORIGINS` | `` | Dev CORS origins — empty in production |

### Separator (all prefixed `MUSEP_`)

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `MUSEP_API_PORT` | `8000` | Separator internal port |
| `MUSEP_MAX_UPLOAD_SIZE_MB` | `200` | Max audio upload size |
| `MUSEP_MP3_BITRATE` | `320` | Output MP3 bitrate |
| `MUSEP_DEVICE` | auto | `cpu`, `cuda`, or `mps` |
| `MUSEP_LALALAI_API_KEY` | `` | LALAL.AI API key (leave blank to disable) |

### Transcription

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `WHISPER_CACHE_DIR` | `/app/.cache/whisper` | Whisper model weights cache directory |

---

## Manual Setup (without Docker)

### Prerequisites

- Python 3.13+
- Node.js 22+
- ffmpeg
- exiftool (optional, for metadata inspection)

```bash
sudo apt install -y ffmpeg libimage-exiftool-perl
```

### Backend

```bash
make install-backend   # creates backend/.venv and installs deps
make backend-dev       # Uvicorn dev server on port 5000
```

### Frontend

```bash
make install-frontend  # npm install in frontend/
make frontend-dev      # Vite dev server on port 5173
```

The Vite dev server proxies `/api/` requests to `http://localhost:5000`.

### Tests

```bash
make test    # pytest on backend
make lint    # flake8 on backend
```

---

## Project Structure

```text
aimusic/
├── backend/              # FastAPI REST API (Uvicorn, port 5000 internal)
│   ├── app/
│   │   ├── __init__.py   # create_app() factory
│   │   ├── main.py       # Uvicorn entry point
│   │   ├── api/          # Routers: auth, admin, download, media, docs, stem, melody, ai
│   │   ├── core/         # AppConfig, JWT auth, security middleware, RBAC
│   │   ├── models/       # User model, SQLite helpers
│   │   ├── services/     # yt-dlp CLI, metadata cleaner, melody extractor
│   │   └── utils/        # safe_media_path(), human_size()
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/             # Vue 3 SPA served by nginx (port APP_PORT)
│   ├── src/
│   │   ├── views/        # Login, Home, Download, MediaFiles, Admin, MyDocs, Melody,
│   │   │                 # DownloadQueue, StorageDashboard, stem/*
│   │   ├── services/     # Axios API client + TypeScript types
│   │   └── stores/       # Pinia auth store
│   ├── Dockerfile        # Multi-stage: Node 22 → nginx 1.27
│   └── nginx.conf
├── separator/            # Stem extraction microservice (port 8000 internal only)
│   ├── src/              # FastAPI API, Demucs/LALAL.AI/AudioSep engines, Click CLI
│   ├── Dockerfile
│   └── requirements.txt
├── transcribe/           # Whisper transcription microservice (port 9000 internal only)
│   ├── src/lib/          # FastAPI service, batch CLI tool
│   ├── Dockerfile
│   └── requirements.txt
├── media/                # Downloaded audio files (bind-mounted volume)
├── docs/                 # My Docs markdown files (bind-mounted volume)
├── data/                 # SQLite database (bind-mounted volume)
├── docker-compose.yml
├── .env.example
├── Makefile
└── CLAUDE.md
```

---

## Using the Web UI

### Login

Navigate to `http://localhost` — you will be redirected to the login page.
Use the superadmin credentials from your `.env` file.

### Download

1. Navigate to **Download** in the top menu.
2. Choose a **Source Type**: `Single` URL, `Playlist` URL, or `Search Text` (one title per line).
3. Pick **Format** (default MP3) and **Bitrate** (default 320k).
4. Optionally set a sub-folder name under **Output Directory**.
5. Enable **Verbose output** to watch yt-dlp logs in real time via SSE.
6. Optionally enable **Auto-transcribe** (Whisper) and/or **Auto-stem** (Demucs) — these run automatically after download completes and stream their progress to the same log view.
7. Click **Start Download**.

### Download Queue

Navigate to **Queue** to see all recent download jobs and their status. Running jobs show a spinner; completed jobs show a success or failure badge. Dismiss finished jobs with the × button. The queue auto-refreshes every 3 seconds while any job is still running.

### Media browser

Navigate to **Media Files** to browse downloaded content.

- **Sorting** — click any column header to sort.
- **Playback** — click **Play** on any audio file to stream in-browser.
- **Download** — click the download icon to save locally.
- **Delete** — tick checkboxes and click **Delete selected**.
- **Metadata** — strip all tags from the current folder via the cleaner panel.
- **Transcribe** — send a file to the Whisper service; a `.md` is written beside it.
- **Melody** — navigate to the Melody Extractor pre-filled with the file path.
- **AI** — open the AI panel to clean transcripts, analyse the song, generate tags, or translate lyrics.

### AI Analysis

The AI panel (✨ button in the media browser) offers four Claude-powered actions:

| Action | Input | Output |
| ------ | ----- | ------ |
| **Clean Transcript** | `.md` transcript file | Corrected punctuation, labelled sections |
| **Analyse Song** | Audio file or transcript | Structure map, themes, lyrical devices |
| **Generate Tags** | Audio file or transcript | Genre, mood, energy, tempo, instruments as JSON |
| **Translate** | Audio file or transcript + target language | Full singable translation with cultural notes |

All actions have a **& Save** variant that writes the result back to disk as a sibling file.
Requires `ANTHROPIC_API_KEY` to be set in `.env`.

### Melody Extractor

Navigate to **Melody** (or click the ♩ button in the media browser) to extract a melody line.

1. Enter the audio file path (pre-filled when navigating from the media browser).
2. Optionally expand **Advanced options** to override BPM, key, mode, pitch range, and HPSS.
3. Click **Extract Melody** — pYIN analysis runs in the background.
4. Download individual outputs (Melody MIDI, Duet MIDI, Lead Sheet MusicXML, Notes CSV) or the full ZIP.
5. Click **Save to Library** to copy outputs alongside the source audio file.

### Stem separation

Navigate to **Stems** to separate audio into individual instrument tracks.

- **Demucs** — local AI model (vocals, drums, bass, guitar, piano, other).
- **LALAL.AI** — cloud-based, requires an API key in `.env`.
- **AudioSep** — text-query separation (requires optional local model install).

### Storage Dashboard

Navigate to **Storage** to see a usage breakdown of your media library — total size, file count, and bar charts by format and folder. Sortable by size or file count.

### My Docs

Navigate to **My Docs** to browse and edit Markdown files in `./docs/`.

- Browse folders, create files/folders, delete, rename.
- **Preview** — rendered Markdown (default view).
- **Editor** — raw Markdown source with toolbar (bold, italic, headings, links, code).
- **Rich-text mode** — WYSIWYG inside the editor tab; saved back as clean Markdown.
- **In-doc links** — clicking a `.md` link opens it in the editor.
- **Search** — full-text search with highlighted snippets.

---

## Makefile Reference

```bash
make help   # list all targets with usage examples
```

### Docker targets

```bash
make up             # docker compose up -d
make down           # docker compose down
make build          # build images (uses current UID/GID)
make rebuild        # build --no-cache then up
make logs           # docker compose logs -f
make restart        # docker compose restart
make ps             # docker compose ps
make backend-shell  # exec bash in the backend container
make frontend-shell # exec sh in the frontend container
```

### Local development

```bash
make install-backend    # create backend/.venv and install deps
make install-frontend   # npm install in frontend/
make backend-dev        # Uvicorn dev server (port 5000)
make frontend-dev       # Vite dev server (port 5173)
make test               # pytest on backend
make lint               # flake8 on backend
```

### Frontend hot-reload with Docker backend

```bash
make up               # start backend in Docker
make frontend-dev     # Vite dev server on port 5173 (proxies /api/ to Docker)
```

### CLI targets

```bash
# Local (uses backend/.venv)
make download URL="https://youtu.be/xyz" FORMAT=mp3 BITRATE=320k OUTPUT=folder
make download QUERY="Artist - Song" SOURCE=single
make clean-meta AUDIO_PATH=media/folder ARGS="--clean --show --backup"
make extract-melody AUDIO=media/song.mp3 MELODY_OUT=results

# Via Docker
make docker-download URL="https://youtu.be/xyz" OUTPUT=folder
make docker-clean-meta MEDIA_PATH=folder ARGS="--clean --show"
make docker-extract-melody AUDIO=media/song.mp3 MELODY_OUT=out
```

---

## Security

- All routes require authentication — JWT cookie (HttpOnly, SameSite=Lax).
- Role-based access enforced at the API layer (`require_roles` dependency in `core/roles.py`) and the UI layer.
- State-changing API endpoints accept JSON only (CSRF protection for SPA).
- Strict Content-Security-Policy — Bootstrap and icons are bundled via npm (no CDN).
- Security headers set in both FastAPI middleware and nginx (`X-Frame-Options`, `X-Content-Type-Options`, etc.).
- File-serving routes use `safe_media_path()` to prevent path traversal.
- Passwords hashed with Werkzeug PBKDF2-SHA256.
- The superadmin account cannot be deleted or have its role changed via the API.
- The Claude API key is server-side only — never exposed to the browser.

---

## Links

- [yt-dlp documentation](https://github.com/yt-dlp/yt-dlp)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Vue 3 documentation](https://vuejs.org/)
- [Pinia documentation](https://pinia.vuejs.org/)
- [Demucs](https://github.com/facebookresearch/demucs)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [Anthropic Claude](https://www.anthropic.com/)
