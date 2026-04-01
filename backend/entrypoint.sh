#!/bin/sh
# entrypoint.sh — run as root, fix volume ownership, then drop to appuser.
#
# Docker bind-mounts created by the daemon are owned by root. This script
# ensures /app/data and /app/media are writable by appuser before handing
# off to gunicorn via gosu.
set -e

chown -R "${APP_USER}:${APP_USER}" /app/data /app/media /app/docs 2>/dev/null || true

exec gosu "${APP_USER}" "$@"
