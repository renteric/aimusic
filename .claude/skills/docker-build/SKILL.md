---
name: docker-build
description: Playbook for building, running, and troubleshooting the Docker stack in the AI-Music project.
---

# Skill: Docker Build & Debug

Use this playbook when building, running, or troubleshooting the Docker stack.

## Build the images

```bash
# Build (uses cache)
docker compose build

# Build with no cache (full rebuild)
docker compose build --no-cache
```

## Start / stop

```bash
docker compose up -d          # start in background
docker compose down           # stop and remove containers
docker compose restart        # restart without rebuilding
```

## Rebuild after code changes

```bash
docker compose up -d --build
```

## View logs

```bash
docker compose logs -f                  # tail all logs
docker compose logs -f backend          # tail backend only
docker compose logs -f frontend         # tail frontend only
```

## Open a shell inside a container

```bash
docker exec -it music-backend /bin/bash
docker exec -it music-frontend /bin/sh
```

## Check image sizes

```bash
docker images ai-powered-music-backend
docker images ai-powered-music-frontend
docker history ai-powered-music-backend --no-trunc
```

## Inspect what is in the backend image

```bash
docker compose run --rm backend find /app -maxdepth 4 -not -path "*/site-packages/*"
```

## Common build failures

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| `apt-get` fails with 404 | Stale package lists | Add `apt-get update` before install |
| `pip` SSL error | Old pip or certs | `pip install --upgrade pip certifi` |
| `Permission denied` on `/app/media` | Volume mounted before `chown` | Ensure `RUN chown` runs before `USER appuser` |
| Gunicorn `ModuleNotFoundError` | Wrong working dir | Verify `WORKDIR /app` in Dockerfile |
| Container exits immediately | App crashes at startup | `docker compose logs backend` to see traceback |
| Frontend 502 Bad Gateway | Backend not healthy yet | Check `docker compose ps`; backend may still be starting |
| SSE stream cuts off | nginx proxy buffering | Ensure `proxy_buffering off` in `nginx.conf` location block |

## Shrink image tips

- Backend base: `python:3.13-slim` not `python:3.13`.
- `--no-install-recommends` in apt.
- `--no-cache-dir` in pip.
- Clean apt lists in same layer.
- Frontend: multi-stage build — only the compiled `dist/` goes into the nginx image.
- Exclude `.venv/`, `media/`, `.git/`, `node_modules/`, `frontend/dist/` in `.dockerignore`.
- Use `dive` to inspect layer sizes: `dive ai-powered-music-backend`.
