# GEMINI.md — AI-Music Project Instructions

This file provides context and rules for Gemini Code Assist. It defines the project standards, architecture, and security requirements.

---

## Project Overview

**AI-Music** is a full-stack application for managing audio (yt-dlp), featuring a **FastAPI** backend, **Vue 3 + TypeScript** frontend, and microservices for transcription (Whisper) and stem separation (Demucs/LALAL.AI).

---

## Architecture & Stack

- **Backend**: Python 3.13, FastAPI (App factory pattern), Uvicorn (Single worker), SQLite (WAL mode).
- **Frontend**: Vue 3 (Composition API, `<script setup lang="ts">`), TypeScript 5.7, Vite 6, Pinia, Bootstrap 5 (npm).
- **Security**: JWT (HttpOnly cookies), RBAC (`superadmin`, `admin`, `user`, `viewer`), CSRF protection (JSON-only endpoints).
- **I18n**: `vue-i18n` (EN, FR, ES), pre-compiled at build time.

---

## Core Coding Standards

### Python (Backend)

- **Format**: Line length **120 characters**.
- **Types**: Strict type hinting. Use `X | Y` union syntax (Python 3.10+), avoid `Optional` or `Union`.
- **Documentation**: Google-style docstrings for all public functions/classes (`Args:`, `Returns:`, `Raises:`).
- **Safety**: Use `backend/app/utils/files.py:safe_media_path()` for ALL file-serving routes.
- **Logic**: Use class-based logic for stateful operations; `@dataclass` for config objects.
- **Async**: Never block the event loop with sync I/O.

### TypeScript & Vue (Frontend)

- **Setup**: Always use `<script setup lang="ts">`.
- **Styling**: No inline styles. Use named classes in `src/assets/css/main.css` (Strict CSP compliance).
- **API**: All calls must go through `src/services/api.ts` with typed responses from `src/services/types.ts`.
- **I18n**: Use `t('key')`. **Crucial**: Never use ASCII apostrophes (`'`) in locale JSON; use typographic right single quotes (`’`) to avoid `vue-i18n` syntax errors.

---

## Role-Based Access Control (RBAC)

- Roles are enforced at the API layer via `Depends(require_roles(...))`.
- `superadmin`: Full access, cannot be deleted or changed.
- `admin`: Full access, cannot modify superadmin.
- `user`: Full media operations, no admin panel.
- `viewer`: Read-only (Browse/Play), cannot Delete, Clean, or Transcribe.

---

## Docker & DevOps

- **Backend Image**: `python:3.13-slim`.
- **Frontend Image**: `node:22-alpine` (builder) → `nginx:1.27-alpine` (runner).
- **Optimization**: Clear APT lists in the same `RUN` layer; use `--no-cache-dir` for pip.
- **Non-root**: Containers must run as non-root users.

---

## What NOT to Do

- **No CDN**: Do not use CDN links for CSS/JS; use npm packages for clean CSP.
- **No hardcoded config**: Use `.env` via `AppConfig`.
- **No multiple workers**: Uvicorn must run with 1 worker to preserve the in-memory `JOBS` state for SSE.
- **No paths outside media/docs**: Always validate paths using the provided utility functions.
- **No `any`**: Avoid `any` in TypeScript; justify with comments if strictly necessary.

---

## Specialized Checklists

Refer to `.gemini/checklists.md` for detailed review steps regarding Docker and Code Review.
Refer to `.gemini/project_memory.md` for historical architectural decisions.
