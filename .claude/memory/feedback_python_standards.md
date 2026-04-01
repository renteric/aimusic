---
name: Python coding standards — classes, reuse, constants, optimization, docstrings
description: All Python code must use class objects, reuse existing classes/functions, centralize constants, be optimized, and have Google-style docstrings on every public symbol.
type: feedback
---

Always follow these rules in every Python file touched or created in this project:

**1. Use class objects — no bare functions for related logic.**
Group related state and behaviour into classes. Use `@dataclass` for value objects (e.g. config, job params). Use plain classes with `__init__` for stateful objects. Never write a collection of module-level functions when a class is the right abstraction.

**2. Reuse existing classes and functions — never duplicate.**
Before writing new code, search the codebase for an existing class, function, or utility that already does the job. Extend or call it instead of copying. Check `backend/app/utils/`, `backend/app/core/`, and `backend/app/services/` first.

**3. Centralize constants — use dedicated constant files.**
Never scatter magic strings, numbers, or enum-like values across files. Add them to an existing constants file (e.g. `backend/app/services/constants.py`) or create a new one in the appropriate module. Import from there everywhere.

**4. Optimize always.**
- Prefer set/dict lookups over list scans.
- Use generators and comprehensions over explicit loops where it is clearer.
- Avoid redundant DB queries — fetch once, pass around.
- Use `async`/`await` correctly; never block the event loop with sync I/O in async context.
- Avoid O(n²) patterns in hot paths.

**5. Docstrings on every public symbol.**
Every module, class, method, and public function must have a Google-style docstring with `Args:`, `Returns:`, and `Raises:` sections where applicable. Private helpers (`_name`) should have docstrings when logic is non-obvious. No exceptions.

**Why:** Consistency, maintainability, and avoiding the tech-debt that accumulates when logic is scattered. These rules apply to every file touched — not just new files.

**How to apply:** When editing any Python file, scan the whole file for violations and fix them in the same change. Do not leave existing undocumented or duplicated code untouched if you are already editing that file.
