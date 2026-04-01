---
name: add-docstrings
description: Playbook for adding or updating Google-style docstrings across Python files in the AI-Music project.
---

# Skill: Add / Update Docstrings

Use this playbook whenever you need to add or update docstrings across Python files.

## Style

Google-style docstrings. Every public symbol gets one.

## Module docstring template

```python
"""
module_name.py - One-line summary.

Longer description of what this module does, its main classes/functions,
and any important usage notes.

Typical usage::

    from module_name import SomeClass
    obj = SomeClass(...)
"""
```

## Class docstring template

```python
class MyClass:
    """One-line summary.

    Longer description if needed.

    Attributes:
        attr_one: Description of attr_one.
        attr_two: Description of attr_two.
    """
```

## Method / function template

```python
def my_function(arg1: str, arg2: int = 0) -> bool:
    """One-line summary.

    Longer explanation if the logic is non-obvious.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2. Defaults to 0.

    Returns:
        Description of what is returned.

    Raises:
        ValueError: When arg1 is empty.
        FileNotFoundError: When the target path does not exist.
    """
```

## Rules

1. One-liner summaries must fit on one line (imperative mood: "Return...", "Resolve...", "Stream...").
2. Include `Args:` only if the function has parameters.
3. Include `Returns:` only if the function returns a non-trivial value.
4. Include `Raises:` only for documented exception paths.
5. Private helpers (`_name`) need docstrings when logic is non-obvious.
6. Do **not** restate the type annotation — describe the *meaning*, not the type.

## Checklist when applying to a file

- [ ] Module-level docstring present
- [ ] Every public class has a class docstring
- [ ] `__init__` documented (or class docstring covers it)
- [ ] Every public method/function has a docstring
- [ ] `dataclass` fields described in class docstring `Attributes:` section
- [ ] No docstring just copies the function name verbatim
