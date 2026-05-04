# ─────────────────────────────────────────────────────────────────────────────
# AI-Music — Transcribe Service Image
# Builder : aimusic-py313-torch (torch 2.6.0+cpu pre-installed)
# Runtime : aimusic-py313 (ffmpeg pre-installed — required by Whisper)
#
# Shared volume: both this container and the backend mount ./media:/app/media,
# so the transcribe service reads audio and writes .md files on the same
# filesystem the UI already browses.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────────────────────────────────────
# torch 2.6.0+cpu is pre-installed in the base — pip will satisfy the
# openai-whisper torch dependency without re-downloading wheels.
FROM ai-music-py313-torch:latest AS builder

COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM ai-music-py313:latest

ARG USER_UID=1000
ARG USER_GID=1000
ARG USER_NAME=rik

# sudo : user management in container setup
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled Python packages from builder (no build tools in this layer)
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Application source — only the lib files needed by the service
COPY src/lib/constants.py          ./src/lib/constants.py
COPY src/lib/transcribe_cli.py     ./src/lib/transcribe_cli.py
COPY src/lib/transcribe_service.py ./src/lib/transcribe_service.py

# Create user/group matching host UID/GID and grant sudo access
RUN groupadd --system --gid "${USER_GID}" ${USER_NAME} || true; \
    useradd  --system --uid "${USER_UID}" --gid "${USER_GID}" \
        --create-home --home-dir /home/${USER_NAME} --shell /bin/bash ${USER_NAME} || true; \
    usermod -aG adm,sudo ${USER_NAME}; \
    printf '%s\n' \
      "${USER_NAME} ALL=(ALL) NOPASSWD: ALL" \
      > /etc/sudoers.d/${USER_NAME}; \
    chmod 440 /etc/sudoers.d/${USER_NAME}

# Default Whisper model cache — overridable via WHISPER_CACHE_DIR env var.
ENV WHISPER_CACHE_DIR=/app/.cache/whisper

RUN mkdir -p /app/media /app/.cache/whisper \
    && chown -R ${USER_NAME}:${USER_NAME} /home/${USER_NAME} /app/media /app/.cache

USER ${USER_NAME}

EXPOSE 9000

CMD ["uvicorn", "src.lib.transcribe_service:app", "--host", "0.0.0.0", "--port", "9000"]
