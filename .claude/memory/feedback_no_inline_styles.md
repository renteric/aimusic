---
name: No inline styles — use CSS classes only
description: Never use style="" or :style="" for static values in Vue templates; add named classes to main.css instead. Required for CSP compliance and no JS vulnerabilities.
type: feedback
---

Never write `style="..."` (static) or `:style="..."` (bound) for static CSS values in Vue templates.

**Why:** Inline styles violate the project's strict Content Security Policy (`style-src 'self'`), may trigger CSP violations in the browser, and are considered an anti-pattern in this codebase.

**How to apply:**
- Always add a named class to `frontend/src/assets/css/main.css` and apply it via `class=` in the template.
- The only acceptable use of `:style` is for truly runtime-dynamic values that cannot be expressed as a class — e.g. a color value fetched from data (`:style="{ background: stem.color }"`). Even then, prefer CSS custom properties or pre-defined color utility classes where possible.
- Before writing any `style=` attribute, ask: can this be a class? If yes, make it a class.
- Group related utility classes semantically in `main.css` with a comment block (e.g. `/* ── Stem player ── */`).
