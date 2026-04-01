# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# AI-Music — Separator Microservice Image
#
# Multi-stage build:
#   builder  — installs all heavy ML deps (torch, demucs, audiosep, etc.)
#   runtime  — minimal image; copies installed packages from builder
#
# src/ is bind-mounted at runtime via docker-compose — not baked in.
# outputs/ is bind-mounted from ../media/stems/ so files land in musicpro's
# shared media volume.
# ─────────────────────────────────────────────────────────────────────────────

# ── Builder stage ─────────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        ffmpeg \
        libsndfile1 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# ── Layer 1: PyTorch (CPU-only, ~300 MB — own layer so it survives requirements changes)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install \
        torch==2.6.0+cpu torchaudio==2.6.0+cpu \
        --index-url https://download.pytorch.org/whl/cpu

# ── Layer 2: Project requirements
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt

# ── Layer 3: AudioSep + its deps
RUN --mount=type=cache,target=/root/.cache/pip \
    git clone --depth=1 https://github.com/Audio-AGI/AudioSep.git /opt/audiosep && \
    pip install transformers laion-clap huggingface_hub lightning && \
    sed -i 's/model\.load_state_dict(ckpt)$/model.load_state_dict(ckpt, strict=False)/' \
        /opt/audiosep/models/CLAP/open_clip/factory.py

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm

ARG USER_UID=1000
ARG USER_GID=1000
ARG USER_NAME=rik

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PYTHONPATH=/opt/audiosep

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        sudo \
        ffmpeg \
        libsndfile1 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create user/group matching host UID/GID and grant sudo access
RUN groupadd --system --gid "${USER_GID}" ${USER_NAME} || true; \
    useradd  --system --uid "${USER_UID}" --gid "${USER_GID}" \
        --create-home --home-dir /home/${USER_NAME} --shell /bin/bash ${USER_NAME} || true; \
    usermod -aG adm,sudo ${USER_NAME}; \
    printf '%s\n' \
      "${USER_NAME} ALL=(ALL) NOPASSWD: ALL" \
      > /etc/sudoers.d/${USER_NAME}; \
    chmod 440 /etc/sudoers.d/${USER_NAME}

WORKDIR /app

# Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# AudioSep source (no setup.py — imported directly via PYTHONPATH)
COPY --from=builder /opt/audiosep /opt/audiosep

# Runtime directories:
#   src/      — separator source (bind-mounted from ../separator/src/)
#   uploads/  — temp audio uploads (separator manages these)
#   outputs/  — bind-mounted from ../media/stems/ (shared volume)
#   models/   — ML model weight cache (persistent volume)
RUN mkdir -p /app/src /app/uploads /app/outputs /app/models && \
    chown -R ${USER_NAME}:${USER_NAME} /app && \
    chmod 755 /app /app/src /app/uploads /app/outputs /app/models

USER ${USER_NAME}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# uvicorn entry — src.api:app maps to separator/src/api.py
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
