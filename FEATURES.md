# AI-Music — Feature Report & Roadmap

*Generated: 2026-03-31*

---

## 1. What's Already Built

### Backend Services

| Area | Details |
|---|---|
| **Downloads** | yt-dlp — single URL, playlist, search query; SSE real-time log streaming |
| **Media browser** | List, stream, download, delete, metadata clean, transcribe |
| **Transcription** | Whisper microservice → `.mp3.md` Markdown output with paragraphs |
| **Stem separation** | Demucs (local ML), LALAL.AI (cloud API), AudioSep (text-query local) |
| **Stem player** | Per-stem volume mix, pitch shift, waveform progress |
| **Melody extraction** | MIDI, MusicXML, BPM detection, key detection — CLI only today |
| **Docs editor** | Markdown files: browse, create, edit, rename, delete, full-text search |
| **Auth** | JWT HttpOnly cookies, RBAC (superadmin / admin / user / viewer) |
| **User management** | Full CRUD admin panel, role assignment, superadmin protection |
| **Metadata cleaner** | Strip/show/backup ID3 tags via exiftool + mutagen |
| **i18n** | English, Français, Español — build-time compiled, CSP-safe |

### API Endpoints (50+)

| Router | Prefix | Key endpoints |
|---|---|---|
| Auth | `/api/auth` | login, logout, me, change-password |
| Admin | `/api/admin` | users CRUD |
| Download | `/api/download` | start job, SSE log stream |
| Media | `/api/media` | files, stream, download, read, delete, clean, transcribe |
| Docs | `/api/docs` | files, file, search, create, update, rename, delete |
| Stem | `/api/stem` | health, models, separate (3 providers), jobs, library |
| Config | `/api/config` | formats, bitrates |

### Frontend Views

| View | Route | What it does |
|---|---|---|
| Home | `/` | Dashboard with feature quick-links |
| Download | `/download` | URL / playlist / search, format/bitrate, live log |
| Media Files | `/media` | Browser, play, transcribe, metadata clean |
| My Docs | `/docs` | Markdown editor, WYSIWYG, search, preview |
| Admin | `/admin` | User management (admin+ only) |
| Profile | `/profile` | Change password, account info |
| Demucs | `/stems/demucs` | Upload → model → stems → download |
| LALAL.AI | `/stems/lalai` | Cloud stem separation |
| AudioSep | `/stems/audiosep` | Text-query separation |
| Stem Library | `/stems/library` | Browse extracted output folders |
| Stem Player | `/stems/player` | Multi-stem mixer with volume per track |

### Infrastructure

| Component | Technology |
|---|---|
| Backend | FastAPI + Uvicorn (1 worker) |
| Frontend | Vue 3 + TypeScript + Vite → nginx |
| Transcription | Whisper microservice (port 9000) |
| Separation | Demucs/LALAL.AI/AudioSep microservice (port 8000) |
| Database | SQLite (WAL mode, no ORM) |
| Auth | JWT + Werkzeug PBKDF2-SHA256 |
| Containers | Docker Compose, non-root users, bind-mounted volumes |

---

## 2. Known Gaps

| Gap | Notes |
|---|---|
| Melody extraction has no UI | CLI exists, no backend route or view yet |
| No stem re-export / bounce | Player mixes volume but can't export a new file |
| No batch operations | Transcribe / separate one file at a time |
| No download queue | Multiple downloads run serially; no queue manager |
| Job state lost on restart | Download jobs are in-memory only |
| No user quotas | Unlimited storage/downloads per user |
| No scheduled tasks | No recurring playlist sync or auto-process |
| Separator needs manual model download | AudioSep checkpoint not auto-fetched |

---

## 3. New Feature Ideas

### A — Claude API Integration (AI Intelligence Layer)

Add `ANTHROPIC_API_KEY` to `.env` and a new `backend/app/api/ai.py` router at `/api/ai/*`.
The key stays server-side — client never sees it.

| Feature | Input | Output |
|---|---|---|
| **Transcription cleanup** | Raw Whisper `.md` transcript | Corrected punctuation, fixed mis-heard words, clean paragraphs |
| **Song analysis** | Transcript + filename | Structure map (verse/chorus/bridge), mood, themes, lyrical devices |
| **Auto-tag generator** | Filename + transcript | Genre, mood, energy level, searchable tags written back to the media entry |
| **Lyric translation** | Transcript + target language | Full translation with cultural notes, saved as a sibling `.md` |
| **Chord progression suggester** | Detected key + BPM + melody | Suggested chord progressions with Roman numeral analysis |
| **Practice notes** | Stem name + instrument | Technique tips, exercises, common patterns for that instrument part |
| **Setlist builder** | List of songs in a folder | Ordered setlist with tempo flow, key transitions, mood arc |
| **Song description** | Any media entry | Human-readable paragraph for sharing, export, or library notes |

All follow the same pattern: read existing data from disk → call Claude → display or save result.

---

### B — Melody Extraction UI

The CLI already works. Zero new ML needed — just connect it.

- **Extract Melody** button on audio files in the media browser
- Shows detected **BPM** and **Key** as badges on the file entry
- Download MIDI and MusicXML directly from the UI
- Reuses `backend/app/services/extract_melody_cli.py`

---

### C — Smart Download Enhancements

- **Download queue** — queue multiple URLs, process one at a time with status
- **Auto-transcribe on download** — optional checkbox; fires transcription immediately after download completes
- **Auto-stem on download** — optional checkbox; fires Demucs immediately after download completes

---

### D — Stem Bouncer (Re-mixer Export)

Extend the existing Stem Player:

- All stems already loaded in browser — add a **Bounce** button
- Send chosen volumes to a new `/api/stem/bounce` endpoint
- Backend runs `ffmpeg` to mix stems at those levels → returns a new MP3
- Result appears in the media library automatically

---

### E — Library Intelligence

- **Duplicate detector** — find files with same duration + similar size
- **Dead transcript cleaner** — flag `.mp3.md` files whose source audio was deleted
- **Storage dashboard** — breakdown by format, folder, total size with charts

---

### F — Scheduled / Automated Tasks

- **Playlist sync** — save a playlist URL + schedule; auto-download new tracks
- **Auto-clean metadata** on all new downloads
- **Auto-transcribe new files** on a watch-folder trigger

---

## 4. Recommended Priority

| Priority | Feature | Effort | Value | Status |
| --- | --- | --- | --- | --- |
| ⭐⭐⭐ | Transcription cleanup + Song analysis (Claude API) | Low | Very High | ✅ Done |
| ⭐⭐⭐ | Auto-tag generator (Claude API) | Low | High | ✅ Done |
| ⭐⭐ | Melody extraction UI | Low | High — CLI already done | ✅ Done |
| ⭐⭐ | Lyric translation (Claude API) | Low | High | ✅ Done |
| ⭐⭐ | Auto-transcribe / auto-stem on download | Medium | High | ✅ Done |
| ⭐ | Stem bouncer / export | Medium | Medium | ✅ Done |
| ⭐ | Download queue manager | Medium | Medium | ✅ Done |
| ⭐ | Storage dashboard | Low | Medium | ✅ Done |

---

## 5. Claude API — How to Add It

### Step 1 — `.env` + `AppConfig`

```env
ANTHROPIC_API_KEY=sk-ant-...
```

```python
# backend/app/core/config.py
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
```

### Step 2 — New router `backend/app/api/ai.py`

```
POST /api/ai/analyse        — song analysis from transcript
POST /api/ai/cleanup        — transcription cleanup
POST /api/ai/translate      — lyric translation
POST /api/ai/tags           — auto-tag generation
POST /api/ai/setlist        — setlist builder
```

Each endpoint:
1. Reads the transcript or metadata from disk using `safe_media_path()`
2. Builds a prompt
3. Calls the Anthropic SDK (async, streaming optional)
4. Returns the result as JSON — or writes it to a sibling `.md` file

### Step 3 — Frontend

A new **AI** button (✨) in the media file actions column opens a panel with the available AI actions for that file.

---

## 6. Tech Stack Reference

| Layer | Technology | Version |
|---|---|---|
| Runtime | Python | 3.13 |
| API framework | FastAPI + Uvicorn | ≥ 0.115 |
| Frontend framework | Vue 3 + TypeScript | ≥ 3.5 |
| Build tool | Vite | ≥ 6.0 |
| State management | Pinia | ≥ 2.3 |
| HTTP client | Axios | ≥ 1.7 |
| CSS framework | Bootstrap 5 (npm) | ≥ 5.3 |
| Markdown | marked | ≥ 15.0 |
| i18n | vue-i18n (precompiled) | ≥ 11.0 |
| Auth | python-jose + Werkzeug | JWT + PBKDF2 |
| Downloader | yt-dlp | latest |
| Transcription | OpenAI Whisper | local |
| Stem separation | Demucs v4 | htdemucs_6s |
| Cloud separation | LALAL.AI API | v1 |
| Text separation | AudioSep | local checkpoint |
| Melody extraction | pYIN + librosa | local |
| Database | SQLite (WAL) | built-in |
| Container | Docker Compose | nginx 1.27 + python:3.13-slim |
