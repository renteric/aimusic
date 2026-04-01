# ─────────────────────────────────────────────────────────────────────────────
# Transcribe Service - Optimized Multi-Stage Docker Image
# Base: python:3.13-slim (Debian Bookworm slim)
#
# Why multi-stage:
#   Stage 1 (builder) installs torch (CPU-only, ~220 MB vs ~2.5 GB CUDA) and
#   all other Python deps. Stage 2 (runtime) copies only site-packages, keeping
#   the final image small and the build fast.
#
# Shared volume:
#   Both this container and the main downloader container mount ./media:/app/media,
#   so the transcribe service reads audio files and writes .md files on the same
#   filesystem the UI already browses.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────────────────────────────────────
# tiktoken 0.7+ ships pre-built wheels for Python 3.13 — no Rust needed.
# torch is installed from the CPU-only index first (~220 MB vs ~2.5 GB CUDA).
FROM python:3.13-slim AS builder

COPY requirements.txt /tmp/requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /tmp/requirements.txt


# ── Stage 2: runtime (slim — no Rust toolchain) ───────────────────────────────
FROM python:3.13-slim

ARG USER_UID=1000
ARG USER_GID=1000
ARG USER_NAME=rik

# ffmpeg is required by Whisper for audio decoding
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled Python packages from builder (no Rust/gcc in this layer)
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Application source — only the lib files needed by the service
COPY src/lib/constants.py        ./src/lib/constants.py
COPY src/lib/transcribe_cli.py   ./src/lib/transcribe_cli.py
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

# Pre-create dirs and placeholders for bind-mounts
RUN mkdir -p /app/media /app/.cache/whisper \
    && chown -R ${USER_NAME}:${USER_NAME} /home/${USER_NAME} /app/media /app/.cache

USER ${USER_NAME}

EXPOSE 9000

CMD ["uvicorn", "src.lib.transcribe_service:app", "--host", "0.0.0.0", "--port", "9000"]
