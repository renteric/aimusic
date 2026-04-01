---
name: Project features and architecture
description: Full-stack FastAPI + Vue 3 + TypeScript with SQLite auth, RBAC, admin panel, and multilingual UI — key decisions and capabilities
type: project
---

Full-stack refactor completed (2026-03-25): monorepo with `backend/` (FastAPI, app factory pattern) and `frontend/` (Vue 3 + TypeScript + Vite 6).

RBAC system added (2026-03-26): four roles, admin panel, role-protected API endpoints.

Multilingual UI added (2026-03-30): English (default), Français, Español. vue-i18n v11, Composition API mode, messages pre-compiled at build time via `@intlify/unplugin-vue-i18n`. Language switcher in NavBar and login page; choice persisted to localStorage.

**Why:** User requested professional-grade site with login auth, latest stack, clean CSP, security-first, and multi-user role management.

**How to apply:** Always use the `backend/app/` package structure and `frontend/src/` layout. Do not revert to the old `src/` flat structure.

## Key architectural decisions

- **SQLite auth + roles**: `backend/app/models/user.py` — WAL mode, `init_db()` creates table + runs inline migration for `role` column, `ensure_superadmin()` promotes first user on existing installs.
- **RBAC decorator**: `backend/app/core/roles.py` — `require_role(*roles)` replaces `@login_required` on role-restricted routes. Always enforce at the API layer regardless of frontend guards.
- **Role hierarchy**: `superadmin` → `admin` → `user` → `viewer`. Superadmin is seeded on first run, cannot be deleted, role cannot be changed via API.
- **Single Gunicorn worker**: SSE job streaming uses in-memory `JOBS` dict; multiple workers each have their own copy → use 1 worker + 4 threads.
- **Bootstrap via npm**: Prevents CDN references so a strict Content-Security-Policy can be applied without `unsafe-inline`.
- **JSON-only endpoints**: All state-changing API endpoints accept `application/json` only → CSRF protection without a CSRF token.
- **Axios 401 interceptor**: Auto-redirects to `/login` on any 401 response — do not duplicate this logic in individual views.
- **SSE + nginx**: `nginx.conf` sets `proxy_buffering off` for the download log stream endpoint.

## Role permissions

| Action | superadmin | admin | user | viewer |
| ------ | ---------- | ----- | ---- | ------ |
| `/admin` page + user CRUD | ✓ | ✓ (not superadmin account) | ✗ | ✗ |
| Download, browse media | ✓ | ✓ | ✓ | ✓ |
| Delete / Metadata Cleaner / Transcribe | ✓ | ✓ | ✓ | ✗ |

## Frontend structure highlights

- `src/services/api.ts` — single Axios instance, `withCredentials: true`, 401 interceptor, `adminApi` for user CRUD
- `src/services/types.ts` — all TypeScript interfaces including `UserRole`, `UserRecord`, admin response types
- `src/stores/auth.ts` — Pinia setup store; exposes `role`, `isAdmin`, `isViewer`; `fetchMe()` called once by router guard
- `src/router/index.ts` — `meta.requiresAdmin: true` blocks non-admin roles at navigation level
- `src/composables/usePlayer.ts` — module-level Audio singleton for audio playback

## Media browser UI features

Sortable file table, in-browser audio player, per-file download/transcribe (hidden for viewer), bulk checkbox delete (hidden for viewer), metadata cleaner panel (hidden for viewer).

## Admin panel (`/admin`)

Bootstrap table listing all users with role badges. Create/edit modal with username, password, role select, active toggle. Delete button disabled for superadmin row. Edit button disabled for superadmin row when logged in as admin (enforced in `openEdit()` guard and `handleSave()` guard, plus backend 403).

## My Docs (`/mydocs`)

Markdown document browser and editor at `frontend/src/views/MyDocsView.vue`. Backend at `backend/app/api/docs.py` (`/api/docs`).

- **List mode**: directory tree browser with sort (name/mtime), create file/folder, bulk delete (viewer: read-only).
- **Editor mode**: source (textarea markdown or contenteditable richtext) + preview tab.
  - Opening a file from the listing → Preview tab; clicking Edit (pencil icon) → Source tab.
  - Toolbar: bold, italic, headings, links, code, text colour, block background colour.
  - Rename in-place via header click.
- **URL sync**: `openEditor` calls `navigateTo(relPath)` when URL doesn't match → browser Back button works correctly. `closeEditor` calls `router.back()`. The route watcher calls `loadOrOpen` on URL changes: paths ending in `.md` reopen the editor, others load the directory.
- **In-doc link navigation**: clicking a `[link](file.md)` in preview opens that file via `openEditor`; Back navigates to the previous document.
- **Full-text search**: debounced search calls `GET /api/docs/search?q=` with highlighted snippets.
- **Viewer role**: create, edit (Source tab), rename, delete hidden — browse and preview only.
