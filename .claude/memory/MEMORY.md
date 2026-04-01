# Memory Index

- [project_features.md](project_features.md) — Architecture decisions: RBAC (4 roles), admin panel, My Docs editor, single worker, SQLite auth, npm Bootstrap, JSON-only endpoints, SSE buffering, multilingual UI (EN/FR/ES)
- [project-context.md](project-context.md) — What the project is, Docker path layout (media, docs, data), Uvicorn setup, gosu entrypoint pattern, i18n architecture
- [mydocs_feature.md](mydocs_feature.md) — /mydocs: URL-synced navigation, router.back() for Back button, loadOrOpen watcher, openEditor tab parameter
- [project_separator_api_only.md](project_separator_api_only.md) — Separator service refactored to API-only: HTML routes/templates removed, transcribe_service.py migrated from Flask to FastAPI
- [feedback_i18n_apostrophes.md](feedback_i18n_apostrophes.md) — Never use ASCII `'` in vue-i18n locale strings; use typographic `'` (U+2019) — crashes the message compiler at runtime
- [feedback_no_inline_styles.md](feedback_no_inline_styles.md) — Never use `style=""` or static `:style=""` in templates; add named classes to main.css instead (CSP + security requirement)
- [feedback_python_standards.md](feedback_python_standards.md) — Python: always use class objects, reuse existing classes/functions, centralize constants, optimize, and add Google-style docstrings to every public symbol
