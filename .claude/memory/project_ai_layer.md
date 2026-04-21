---
name: Claude AI intelligence layer
description: AI features added in April 2026 — transcript cleanup and song analysis via Claude API
type: project
---

POST /api/ai/cleanup and POST /api/ai/analyse added in backend/app/api/ai.py.

**Why:** First phase of the Claude API integration (FEATURES.md §4, priority ⭐⭐⭐). Reads Whisper transcripts from disk, calls Claude sonnet-4-6, returns cleaned/analysed text. Optional `save: true` writes results back to disk.

**How to apply:** When extending AI features, follow the same pattern: `safe_media_path()` → build prompt → `_call_claude()` → return JSON. Model constant is `_MODEL` at the top of ai.py. Next priorities from FEATURES.md: auto-tag generator and lyric translation.
