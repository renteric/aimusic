---
name: add-feature
description: Playbook for adding a new audio format, bitrate, FastAPI endpoint, Vue view, config option, CLI option, or Pinia store to the AI-Music project.
---

# Skill: Add a New Feature

Playbook for adding a new download source, format, UI option, or API endpoint.

## Adding a new audio format

1. `backend/app/services/constants.py` — append the extension to `SUPPORTED_FORMATS`.
2. `frontend/src/services/types.ts` — add the new format to the `AudioFormat` union type if one exists.
3. Test via the web UI and via CLI:

   ```bash
   make download URL="..." FORMAT=<new_format>
   ```

## Adding a new bitrate

1. `backend/app/services/downloader_cli.py` — append to `SUPPORTED_BITRATES`.

## Adding a new FastAPI endpoint

1. Add the route to the appropriate router in `backend/app/api/`:
   - Auth-related → `auth.py`
   - User management → `admin.py`
   - Download-related → `download.py`
   - Media file-related → `media.py`
2. Use `Depends(require_roles(...))` from `backend/app/core/roles.py` to enforce access:
   - Open to all authenticated users → `Depends(require_roles("superadmin", "admin", "user", "viewer"))`
   - Blocked for viewer → `Depends(require_roles("superadmin", "admin", "user"))`
   - Admin panel only → `Depends(require_roles("superadmin", "admin"))`
3. Accept JSON for POST/PUT/DELETE (CSRF protection for SPA).
4. Use `safe_media_path()` from `backend/app/utils/files.py` if the route serves or operates on files.
5. Add full type hints and a Google-style docstring.
6. Register the router in `backend/app/__init__.py` via `create_app()` if creating a new router.

## Adding role restrictions to a Vue view or component

1. Import the auth store: `import { useAuthStore } from '@/stores/auth'`
2. Use `auth.isViewer` to hide destructive actions for viewers.
3. Use `auth.isAdmin` to show admin-only UI elements (e.g. admin nav link).
4. Add `meta: { requiresAdmin: true }` to the route record in `router/index.ts` to block non-admin navigation entirely.
5. Always back UI restrictions with backend `@require_role(...)` enforcement.

## Adding a new Vue view

1. Create the view component in `frontend/src/views/` (e.g. `MyView.vue`).
2. Use `<script setup lang="ts">`.
3. Add the route to `frontend/src/router/index.ts`.
4. Add a nav link in `frontend/src/components/NavBar.vue` if user-facing.
5. Add required API calls to `frontend/src/services/api.ts` and types to `types.ts`.

## Adding a new config option

1. Add the env var to `.env.example` with a comment.
2. Add a class attribute to `AppConfig` in `backend/app/core/config.py`:

   ```python
   NEW_OPTION: str = os.getenv("NEW_OPTION", "default_value")
   ```

3. Document it in `CLAUDE.md` under "Environment Variables".

## Adding a new CLI option to downloader_cli.py

1. Add a `@click.option(...)` decorator to `main()` in `backend/app/services/downloader_cli.py`.
2. Add the corresponding field to `DownloadConfig` if it affects the download.
3. Pass it through to `_download_media()` via the config object.
4. Add the corresponding Make variable and CLI flag to the `download` target in `Makefile`.
5. Update the module docstring examples if behaviour changes.

## Adding a new Pinia store

1. Create `frontend/src/stores/<name>.ts`.
2. Use `defineStore` with setup syntax.
3. Export the store and import it in the components that need it.
4. Keep only global/shared state — local component state belongs in `ref`/`reactive` in the component.
