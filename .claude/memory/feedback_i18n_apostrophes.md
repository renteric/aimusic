---
name: vue-i18n apostrophe rule
description: ASCII apostrophes in locale JSON strings crash the vue-i18n message compiler — always use the typographic right single quote instead
type: feedback
---

Never use ASCII apostrophe `'` (U+0027) in vue-i18n locale JSON strings. The message
compiler treats it as an escape character and throws a `SyntaxError` at runtime, even
when messages are pre-compiled by the Vite plugin.

**Why:** Spent multiple build/deploy cycles chasing this bug across fr.json, en.json, and
es.json. The `''` double-escape workaround is fragile because it only works in specific
parser states. The issue affects all vue-i18n versions (v9, v10, v11).

**How to apply:** When writing or editing any locale file (`en.json`, `fr.json`, `es.json`),
replace every apostrophe with the typographic right single quote `'` (U+2019). Examples:
- `"Meta's"` → `"Meta\u2019s"`
- `"l'audio"` → `"l\u2019audio"`
- `"s'est"` → `"s\u2019est"`

After editing locale files, grep for bare apostrophes before rebuilding:
`grep -n "[^']'[^']" frontend/src/i18n/locales/*.json`
