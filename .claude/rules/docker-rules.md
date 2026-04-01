# Docker Rules — AI-Music

## Base Image

Always use `python:3.13-slim` (Debian Bookworm slim).

- **Not** `python:3.13-alpine` — ffmpeg compilation is complex on musl libc.
- **Not** `python:3.13` (full) — ~500 MB heavier than slim for no benefit.

## Layer Caching Strategy

Order `COPY` + `RUN` instructions from least-to-most likely to change:

1. System deps (`apt-get install`) — changes rarely.
2. Python deps (`pip install -r requirements.txt`) — changes on dep updates.
3. Application source (`COPY app/`) — changes on every code edit.

This ensures Docker reuses cached layers on most rebuilds.

## APT Best Practices

Always clean up in the **same** `RUN` layer to keep the layer small:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libimage-exiftool-perl \
        gosu \
        nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```

- `--no-install-recommends` — skip suggested packages.
- `apt-get clean` + `rm -rf /var/lib/apt/lists/*` — remove package cache.
- `gosu` — needed by the entrypoint to drop from root to appuser after chowning volumes.
- `nodejs` — required by yt-dlp for YouTube JS extraction.

## Pip Best Practices

```dockerfile
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt
```

- `--no-cache-dir` — skip local pip cache (saves image space).
- Upgrade pip first to avoid resolver issues with newer packages.

## Security — Non-Root User + Volume Ownership

The container uses a `gosu`-based entrypoint pattern so bind-mounted volumes
(created as root by Docker) can be chowned before dropping privileges:

```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /app/media /app/data \
    && chown -R appuser:appuser /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

`entrypoint.sh` runs as root, chowns `/app/data` and `/app/media`, then execs
the app as `appuser` via `gosu`. Do **not** add `USER appuser` to the Dockerfile
— let the entrypoint handle the switch.

## .dockerignore

The following must always be excluded:

- `.venv/` — never copy virtual env into the image; reinstall inside.
- `media/` — runtime data, mounted as a volume.
- `.env` — secrets must not be baked into the image.
- `__pycache__/`, `*.pyc` — Python bytecode.
- `.git/` — version history adds size with no runtime benefit.

## docker-compose.yml Rules

- Use `env_file: .env` so all config comes from one place.
- Expose the port dynamically: `"${APP_PORT:-80}:80"` for nginx.
- Mount `./media` and `./data` as bind volumes so files persist across restarts.
- Add a `healthcheck` so `docker compose ps` shows real health status.
- Use `restart: unless-stopped` for production-like reliability.
- Run `mkdir -p media data` before `docker compose up` (done by `make up`).

## Gunicorn Settings

**Always use 1 worker.** The `JOBS` in-memory dict is not shared across workers —
multiple workers break SSE log streaming.

```
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 300 app.main:app
```

- `--workers 1` — required; SSE job registry is in-memory.
- `--threads 4` — allows concurrent requests (browsing while downloading).
- `--timeout 300` — long downloads must not kill the worker.
- `--access-logfile -` and `--error-logfile -` — log to stdout/stderr for
  `docker compose logs` visibility.
