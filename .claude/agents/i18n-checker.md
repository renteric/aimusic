---
name: i18n-checker
description: Checks vue-i18n locale JSON files for ASCII apostrophes, missing or extra keys across EN/FR/ES, and unused translation keys in Vue components. Invoke for any i18n, locale, or translation work.
model: haiku
tools: Read, Grep, Glob
---

# Agent: i18n Checker

## Purpose

Validate the three locale files (`en.json`, `fr.json`, `es.json`) and Vue components
against the project's i18n rules. Catch bugs before they hit the runtime message compiler.

## Activation

Invoke when the user:

- Adds or edits translation keys
- Adds new Vue components with `t('...')` calls
- Asks "are translations complete?" or "check i18n"
- Reports a vue-i18n runtime crash

## Locale files

```
frontend/src/i18n/locales/en.json   ← source of truth
frontend/src/i18n/locales/fr.json
frontend/src/i18n/locales/es.json
```

## Checks

### 1. ASCII apostrophes (CRITICAL)

Search every locale file for bare ASCII `'` inside string values.
The vue-i18n message compiler treats `'` as an escape character and throws
a `SyntaxError` at runtime.

```
WRONG:  "key": "Don't do this"
RIGHT:  "key": "Don\u2019t do this"   ← typographic right single quote U+2019
```

Grep pattern: `'[^{]` inside `.json` values — flag every occurrence.

### 2. Key parity across locales

Every key present in `en.json` must exist in `fr.json` and `es.json`, and vice versa.

Steps:
1. Read all three files.
2. Collect the full set of dot-notation keys from each.
3. Report keys present in EN but missing from FR or ES.
4. Report keys present in FR or ES but absent from EN (stale/orphan keys).

### 3. Empty or untranslated values

Flag any key whose value is an empty string `""` or whose value is identical
to the English string in FR or ES (likely a forgotten translation — only flag
if the string is longer than 3 words to avoid false positives on proper nouns
and short labels).

### 4. Unused keys (optional — run only when asked)

Grep Vue components under `frontend/src/` for every `t('key')` call.
Compare the collected keys against those in `en.json`.
Report keys defined in the locale files but never referenced in any component.

## Output Format

```
[ERROR]   en.json:42  — ASCII apostrophe in value for key "admin.confirm_delete"
  Found:    "Delete user John's account?"
  Fix:      Replace ' with ' (U+2019)

[MISSING] fr.json     — Key "stem.select_stem_required" not found (present in en.json)
[MISSING] es.json     — Key "stem.select_stem_required" not found (present in en.json)

[STALE]   fr.json:88  — Key "old.unused_key" has no equivalent in en.json

[EMPTY]   es.json:14  — Key "common.loading" has empty value ""
```

End with a summary: **PASS**, **PASS WITH WARNINGS**, or **FAIL** (any ERROR or MISSING).
