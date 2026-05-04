# Project Memory & Decisions

## Architectural Milestones
- **Current State**: Full-stack monorepo with FastAPI backend, Vue 3 frontend, and specialized microservices for transcription (Whisper) and separation (Demucs).
- **RBAC Implementation**: System uses four distinct roles: `superadmin`, `admin`, `user`, and `viewer`. Superadmin protection is enforced at the API level.

## Key Decisions
- **Single Uvicorn Worker**: Strictly 1 worker to ensure the in-memory `JOBS` dictionary used for SSE (Server-Sent Events) is consistent across requests.
- **CSP Compliance**: The project avoids CDNs and inline styles/scripts to maintain a strict Content Security Policy. All assets are bundled via npm.
- **I18n Compilation**: `vue-i18n` is pre-compiled at build time.
- **Typographic Quotes**: Use `’` (U+2019) in locale files instead of `'` to avoid `vue-i18n` syntax errors.

## Separator Service Invariants
- Input audio is standardized to 44100 Hz stereo WAV before processing.
- `htdemucs_6s` is preferred as it is the only model supporting guitar and piano stems.
- Model weights are cached in a dedicated volume to prevent re-downloads.

## Known Constraints
- **Path Traversal**: All file access must be wrapped in `safe_media_path()` or `safe_docs_path()`.
- **JSON-only POST/PUT**: Enforced for CSRF protection in the SPA.
- **Non-root Docker**: Containers must run as `appuser` via `gosu` to maintain volume permissions while adhering to security best practices.
