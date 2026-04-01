#!/usr/bin/env bash
# .claude/hooks/lint.sh
#
# Run all linters and formatters against the source tree.
# Usage: bash .claude/hooks/lint.sh [--fix]
#
# With --fix: applies black and isort formatting automatically.
# Without:    runs in check mode only (non-zero exit on any issue).

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

FIX=false
for arg in "$@"; do
    [[ "$arg" == "--fix" ]] && FIX=true
done

run() { echo "==> $*"; "$@"; }

VENV="backend/.venv/bin"

# ── black ─────────────────────────────────────────────────────────────────────
if [ -x "$VENV/black" ]; then
    if $FIX; then
        run "$VENV/black" --line-length 120 backend/app/
    else
        run "$VENV/black" --check --line-length 120 backend/app/
    fi
else
    echo "SKIP: black not found (run: make install-backend)"
fi

# ── isort ─────────────────────────────────────────────────────────────────────
if [ -x "$VENV/isort" ]; then
    if $FIX; then
        run "$VENV/isort" --profile black --line-length 120 backend/app/
    else
        run "$VENV/isort" --check-only --profile black --line-length 120 backend/app/
    fi
else
    echo "SKIP: isort not found (run: make install-backend)"
fi

# ── flake8 ────────────────────────────────────────────────────────────────────
if [ -x "$VENV/flake8" ]; then
    run "$VENV/flake8" backend/app/
else
    echo "SKIP: flake8 not found (run: make install-backend)"
fi

# ── vue-tsc ───────────────────────────────────────────────────────────────────
if [ -f frontend/node_modules/.bin/vue-tsc ]; then
    run frontend/node_modules/.bin/vue-tsc --noEmit
else
    echo "SKIP: vue-tsc not found (run: make install-frontend)"
fi

echo ""
echo "Done. Use --fix to auto-format Python code."
