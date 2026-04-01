#!/usr/bin/env bash
# .claude/hooks/pre-commit.sh
#
# Run this before committing to catch common issues.
# Usage: bash .claude/hooks/pre-commit.sh
#
# To install as a git hook:
#   cp .claude/hooks/pre-commit.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "==> Checking for .env in staged files..."
if git diff --cached --name-only | grep -qE '^\.env$'; then
    echo "ERROR: .env is staged for commit. Remove it: git reset HEAD .env"
    exit 1
fi

echo "==> Running flake8 on backend..."
if [ -x backend/.venv/bin/flake8 ]; then
    backend/.venv/bin/flake8 backend/app/
else
    echo "SKIP: backend/.venv/bin/flake8 not found (run: make install-backend)"
fi

echo "==> Running vue-tsc on frontend..."
if [ -f frontend/node_modules/.bin/vue-tsc ]; then
    cd frontend && node_modules/.bin/vue-tsc --noEmit && cd "$ROOT"
else
    echo "SKIP: vue-tsc not found (run: make install-frontend)"
fi

echo "==> Checking for hardcoded secrets patterns in Python files..."
if git diff --cached -- "*.py" | grep -qE '(password|secret_key|api_key)\s*=\s*["\x27][^"\x27]{8,}'; then
    echo "WARNING: Possible hardcoded secret detected in staged Python files. Review carefully."
fi

echo "==> All checks passed."
