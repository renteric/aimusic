# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# AI-Music — Separator Microservice Image
#
# Builder : ai-music-py313-torch (torch 2.6.0+cpu) + git to clone AudioSep code
# Runtime : ai-music-py313 (ffmpeg, libsndfile1, curl pre-installed)
#
# Model weights are NOT baked into the image — they are bind-mounted at runtime:
#   ./models/separator/audiosep → /app/models/audiosep  (AudioSep checkpoint)
#   ./models/separator/torch    → /app/models/torch     (Demucs cache)
# Run `make download-separator` once to populate those host directories.
#
# src/ is bind-mounted at runtime via docker-compose — not baked in.
# outputs/ is bind-mounted from ../media/stems/ so files land in the
# shared media volume.
# ─────────────────────────────────────────────────────────────────────────────

# ── Builder stage ─────────────────────────────────────────────────────────────
FROM ai-music-py313-torch:latest AS builder

# git : clone AudioSep Python source (the repo code, not the weights)
# build-essential : laion-clap pins numpy 1.26.x which has no Python 3.13 wheel
#   and must compile from source; compiler stays in the builder stage only.
RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Project requirements (torch 2.6.0+cpu already in base — pip skips it)
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt

# Clone AudioSep Python source and install its runtime deps.
# The CLAP checkpoint is NOT downloaded here — it is bind-mounted at runtime.
# The sed patch fixes a strict= mismatch introduced in torch 2.x.
RUN --mount=type=cache,target=/root/.cache/pip \
    git clone --depth=1 https://github.com/Audio-AGI/AudioSep.git /opt/audiosep && \
    pip install transformers laion-clap huggingface_hub lightning && \
    sed -i 's/model\.load_state_dict(ckpt)$/model.load_state_dict(ckpt, strict=False)/' \
        /opt/audiosep/models/CLAP/open_clip/factory.py

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM ai-music-py313:latest

ARG USER_UID=1000
ARG USER_GID=1000
ARG USER_NAME=rik

# PYTHONUNBUFFERED, PYTHONDONTWRITEBYTECODE, PYTHONHASHSEED are inherited from base.
ENV PYTHONPATH=/opt/audiosep

# sudo : needed for user management during container startup
RUN apt-get update && \
    apt-get install -y --no-install-recommends sudo && \
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

# AudioSep Python source (imported via PYTHONPATH — no setup.py)
COPY --from=builder /opt/audiosep /opt/audiosep

# Runtime directories — models/ is populated by bind-mounts, not baked in
RUN mkdir -p /app/src /app/uploads /app/outputs /app/models && \
    chown -R ${USER_NAME}:${USER_NAME} /app && \
    chmod 755 /app /app/src /app/uploads /app/outputs /app/models

USER ${USER_NAME}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
