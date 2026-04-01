# ─────────────────────────────────────────────────────────────────────────────
# AI-Music — Backend API Image
# Base: python:3.13-slim (Debian Bookworm slim)
#
# Layer order: system deps → Python deps → source code
# This maximises Docker cache hits: source-only changes skip the pip layer.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.13-slim

ARG USER_UID=1000
ARG USER_GID=1000
ARG USER_NAME=rik

# ── System dependencies ───────────────────────────────────────────────────────
# ffmpeg                 : audio conversion (required by yt-dlp)
# libimage-exiftool-perl : metadata reading/writing (used by metadata_cleaner)
# gosu                   : drop from root to app user in entrypoint
# nodejs                 : required by yt-dlp for YouTube JS extraction
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libimage-exiftool-perl \
        gosu \
        nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy only requirements first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY app/ ./app/

# ── Non-root user ─────────────────────────────────────────────────────────────
# The entrypoint runs as root, chowns the bind-mounted volumes, then execs
# uvicorn via gosu to drop back to the app user.
RUN groupadd -g "${USER_GID}" "${USER_NAME}" \
    && useradd -u "${USER_UID}" -g "${USER_NAME}" -d /app -s /sbin/nologin "${USER_NAME}" \
    && mkdir -p /app/media /app/data \
    && chown -R "${USER_NAME}:${USER_NAME}" /app

# Pass the runtime username to the entrypoint via ENV
ENV APP_USER=${USER_NAME}

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

# ── Uvicorn ───────────────────────────────────────────────────────────────────
# Single worker: in-memory JOBS dict must not be split across workers.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", \
     "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--workers", "1", \
     "--timeout-keep-alive", "300", \
     "--access-log"]
