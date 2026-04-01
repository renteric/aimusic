# Coding Standards — AI-Music

## Python Version

Always target **Python 3.13**. Use modern syntax:

- Union types: `X | Y` (not `Optional[X]` or `Union[X, Y]`)
- `match` / `case` for multi-branch dispatch where it improves clarity
- `dataclasses.dataclass` for pure data holders

## Type Hints

All public function signatures must be fully annotated:

```python
# Good
def resolve_output_dir(output: str) -> Path: ...

# Bad — missing return type
def resolve_output_dir(output: str): ...
```

## Docstrings

Use **Google style** with explicit sections:

```python
def my_func(x: int, y: str) -> bool:
    """One-line summary.

    Longer description if needed. Can be multiple sentences.

    Args:
        x: Description of x.
        y: Description of y.

    Returns:
        Description of the return value.

    Raises:
        ValueError: When x is negative.
    """
```

Rules:

- Every public class, method, and function must have a docstring.
- Module-level docstring required in every `.py` file.
- Private helpers (`_name`) should have docstrings when the logic is non-obvious.

## Configuration

- All runtime settings live in `.env` and are read through `AppConfig` in `backend/app/core/config.py`.
- Never hardcode ports, paths, secrets, or timeouts.
- When adding a new setting: add to `.env.example`, `AppConfig`, and `CLAUDE.md`.

## Objects / Data Classes

- Use `@dataclass` for value objects (e.g. `DownloadConfig`).
- Use plain classes with `__init__` for stateful objects (e.g. `DownloadJob`).
- Add `__post_init__` validation in dataclasses that enforce invariants.

## Error Handling

- Validate at system boundaries (CLI args, JSON request bodies, file paths).
- Re-raise or wrap with context instead of silently swallowing exceptions.
- Never `except Exception: pass`.
- Never expose stack traces or internal paths to the HTTP response.

## Line Length & Formatting

- Max line length: **120 characters**.
- Format with **black** (line-length 120).
- Sort imports with **isort** (profile = black).
- Lint with **flake8** (see `pyproject.toml`).

## Security (Python)

- Always sanitise user-supplied file paths with `safe_media_path()` from `backend/app/utils/files.py`.
- Never expose stack traces or internal paths to HTTP responses.
- `SECRET_KEY` must be a long random string in production — never the default.
- All state-changing endpoints must accept JSON only (prevents CSRF for SPA).

---

## TypeScript / Vue Standards

### TypeScript

- Strict mode required (`"strict": true` in `tsconfig.json`).
- No `any` types. If unavoidable, add a comment explaining why.
- Define all API response shapes in `frontend/src/services/types.ts`.
- Prefer `interface` over `type` for object shapes.
- Use `readonly` for props and immutable data.

### Vue 3 Single File Components

- Always use `<script setup lang="ts">` — no Options API.
- Component names: `PascalCase` (both file name and registration).
- Props defined with `defineProps<{ ... }>()` — typed, no runtime validators needed.
- Emits defined with `defineEmits<{ ... }>()`.
- Composables in `src/composables/` — always prefix with `use` (e.g. `usePlayer`).
- Do not put business logic in views — extract to composables or `src/services/api.ts`.

### Pinia Stores

- Use `defineStore` with setup syntax (not options syntax).
- Store files in `src/stores/`; one store per domain (e.g. `auth.ts`).
- Keep stores lean — only global shared state (not local component state).

### Axios / API layer

- All API calls go through the Axios instance in `src/services/api.ts`.
- Always set `withCredentials: true` (session cookie auth).
- The 401 interceptor auto-redirects to `/login` — do not duplicate this logic in views.
- Return typed responses — no `any` in API function return types.

### CSS / Styling

- Bootstrap 5 installed via npm — never use CDN links.
- Custom overrides in `src/assets/css/main.css` only.
- No inline styles in templates.
- Use Bootstrap utility classes first; add custom CSS only when utilities are insufficient.
