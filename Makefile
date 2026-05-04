# ─────────────────────────────────────────────────────────────────────────────
# AI-Music — Makefile
# Run `make help` for a list of available targets.
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_CONTAINER = music-backend
FRONTEND_CONTAINER = music-frontend
PYTHON             = backend/.venv/bin/python3

# ── Download variables ─────────────────────────────────────────────────────────
SOURCE    ?= single
URL       ?=
QUERY     ?=
FORMAT    ?= mp3
BITRATE   ?= 320k
OUTPUT    ?=
VERBOSE   ?=
FORCE     ?=

# ── Metadata cleaner variables ─────────────────────────────────────────────────
AUDIO_PATH ?=
MEDIA_PATH ?=
ARGS       ?=

# ── Melody extractor variables ─────────────────────────────────────────────────
AUDIO       ?=
MELODY_OUT  ?= out
FMIN        ?= C4
FMAX        ?= A6
MIN_NOTE_MS ?=
NO_HPSS     ?=
BPM         ?=
KEY         ?=
MODE        ?=
HARMONY     ?=

.PHONY: help \
        build-bases \
        up down build rebuild logs restart ps \
        backend-shell frontend-shell \
        frontend-dev backend-dev \
        install-backend install-frontend \
        test lint \
        download clean-meta extract-melody \
        docker-download docker-clean-meta docker-extract-melody \
        download-acestep download-separator

# ── Help ───────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  Docker (production)"
	@echo "  ──────────────────────────────────────────────────────────"
	@echo "  make build-bases                 Build shared base images (run once, or when system deps change)"
	@echo "  make download-acestep            Download ACE-Step model weights (~10 GB) to ./models/acestep/"
	@echo "  make download-separator          Download AudioSep (~1 GB) + CLAP encoder (~900 MB) + Demucs (~85 MB) to ./models/separator/"
	@echo "  make up                          Start all services (detached)"
	@echo "  make down                        Stop and remove containers"
	@echo "  make build                       Build Docker images (requires base images)"
	@echo "  make rebuild                     Rebuild everything from scratch, no cache"
	@echo "  make logs                        Tail all container logs"
	@echo "  make restart                     Restart all services"
	@echo "  make ps                          Show container health/status"
	@echo "  make backend-shell               Open bash in the backend container"
	@echo "  make frontend-shell              Open sh in the frontend container"
	@echo ""
	@echo "  Local development"
	@echo "  ──────────────────────────────────────────────────────────"
	@echo "  make install-backend             Install backend Python deps into .venv"
	@echo "  make install-frontend            Install frontend npm deps"
	@echo "  make backend-dev                 Run Uvicorn in dev mode (port 5000)"
	@echo "  make frontend-dev                Run Vite dev server (port 5173)"
	@echo "  make test                        Run pytest on the backend"
	@echo "  make lint                        Run flake8 on the backend"
	@echo ""
	@echo "  CLI — local (uses backend/.venv)"
	@echo "  ──────────────────────────────────────────────────────────"
	@echo "  make download URL=<url>  [SOURCE=single|playlist] [FORMAT=mp3] [BITRATE=320k] [OUTPUT=folder]"
	@echo "  make clean-meta AUDIO_PATH=<path> [ARGS='--clean --show --backup']"
	@echo ""
	@echo "  CLI — via Docker"
	@echo "  ──────────────────────────────────────────────────────────"
	@echo "  make docker-download URL=<url>   [SOURCE=single] [FORMAT=mp3] [OUTPUT=folder]"
	@echo "  make docker-clean-meta MEDIA_PATH=<subfolder> [ARGS='--clean --show --backup']"
	@echo ""

# ── Docker ─────────────────────────────────────────────────────────────────────

# Build the two shared base images.  Service Dockerfiles FROM these, so bases
# must exist before `make build`.  BuildKit cache makes subsequent runs instant.
build-bases:
	docker build \
		-f docker/Dockerfile.base \
		-t ai-music-py313:latest \
		.
	docker build \
		-f docker/Dockerfile.torch-base \
		-t ai-music-py313-torch:latest \
		.

# Download ACE-Step model weights to ./models/acestep/ on the host.
# Runs entirely via Docker — no local Python or pip required.
# After completion, set ACESTEP_CHECKPOINT_PATH=/app/models/checkpoints in .env.
download-acestep:
	@mkdir -p models/acestep
	@echo "Downloading ACE-Step/ACE-Step-v1-3.5B (~10 GB) to ./models/acestep/ ..."
	docker run --rm -t \
		-v "$(CURDIR)/models/acestep:/models" \
		$(if $(HUGGINGFACE_HUB_API_KEY),-e HF_TOKEN="$(HUGGINGFACE_HUB_API_KEY)") \
		python:3.13-slim \
		sh -c "pip install -q --root-user-action=ignore huggingface_hub && \
		       python -c \"from huggingface_hub import snapshot_download; \
		                   snapshot_download('ACE-Step/ACE-Step-v1-3.5B', local_dir='/models')\""
	@echo ""
	@echo "Done. Now set in .env:"
	@echo "  ACESTEP_CHECKPOINT_PATH=/app/models/checkpoints"
	@echo "Then restart: docker compose restart acestep"

# Download separator model weights to ./models/separator/ on the host.
# - AudioSep checkpoint (~1 GB) from HuggingFace → ./models/separator/audiosep/
# - Demucs htdemucs_6s (~85 MB) via the separator image → ./models/separator/torch/
# Both run via Docker — no local Python or pip required.
download-separator:
	@mkdir -p models/separator/audiosep models/separator/clap models/separator/torch
	@echo "Downloading AudioSep checkpoint (~1 GB) ..."
	docker run --rm -t \
		-v "$(CURDIR)/models/separator/audiosep:/models" \
		$(if $(HUGGINGFACE_HUB_API_KEY),-e HF_TOKEN="$(HUGGINGFACE_HUB_API_KEY)") \
		python:3.13-slim \
		sh -c "pip install -q --root-user-action=ignore huggingface_hub && \
		       python -c \"from huggingface_hub import hf_hub_download; \
		                   hf_hub_download('audo/AudioSep', \
		                                  'audiosep_base_4M_steps.ckpt', \
		                                  local_dir='/models')\""
	@echo "Downloading CLAP encoder weights (~900 MB) ..."
	docker run --rm -t \
		-v "$(CURDIR)/models/separator/clap:/models" \
		$(if $(HUGGINGFACE_HUB_API_KEY),-e HF_TOKEN="$(HUGGINGFACE_HUB_API_KEY)") \
		python:3.13-slim \
		sh -c "pip install -q --root-user-action=ignore huggingface_hub && \
		       python -c \"from huggingface_hub import hf_hub_download; \
		                   hf_hub_download('lukewys/laion_clap', \
		                                  'music_speech_audioset_epoch_15_esc_89.98.pt', \
		                                  local_dir='/models')\""
	@echo "Downloading Demucs htdemucs_6s model (~85 MB) ..."
	docker run --rm -t \
		-v "$(CURDIR)/models/separator/torch:/app/models/torch" \
		-e TORCH_HOME=/app/models/torch \
		ai-music-separator:latest \
		python -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')"
	@echo ""
	@echo "Done. Models are in ./models/separator/ and will be used automatically"
	@echo "on next 'docker compose up' (no .env changes needed)."

up:
	@mkdir -p media data models/acestep models/separator/audiosep models/separator/clap models/separator/torch
	docker compose up -d

down:
	docker compose down

build: build-bases
	docker compose build \
		--build-arg USER_UID=$(shell id -u) \
		--build-arg USER_GID=$(shell id -g) \
		--build-arg USER_NAME=$(shell whoami)

rebuild:
	docker build --no-cache \
		-f docker/Dockerfile.base \
		-t ai-music-py313:latest \
		.
	docker build --no-cache \
		-f docker/Dockerfile.torch-base \
		-t ai-music-py313-torch:latest \
		.
	docker compose build --no-cache \
		--build-arg USER_UID=$(shell id -u) \
		--build-arg USER_GID=$(shell id -g) \
		--build-arg USER_NAME=$(shell whoami)
	docker compose up -d

bk-rebuild:
	docker compose build backend && docker compose up backend -d

fe-rebuild:
	docker compose build frontend && docker compose up frontend -d

logs:
	docker compose logs -f

restart:
	docker compose restart

ps:
	docker compose ps

backend-shell:
	docker exec -it $(BACKEND_CONTAINER) /bin/bash

frontend-shell:
	docker exec -it $(FRONTEND_CONTAINER) /bin/sh

# ── Local development ──────────────────────────────────────────────────────────

install-backend:
	cd backend && python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt

install-frontend:
	cd frontend && npm install

backend-dev:
	cd backend && .venv/bin/python -m app.main

frontend-dev:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest

lint:
	cd backend && .venv/bin/flake8 app/

# ── CLI — local ────────────────────────────────────────────────────────────────

download:
	cd backend && PYTHONPATH=app/services $(PYTHON) app/services/downloader_cli.py \
		-s $(SOURCE) \
		$(if $(URL),-u "$(URL)") \
		$(if $(QUERY),-q "$(QUERY)") \
		--format $(FORMAT) \
		--bitrate $(BITRATE) \
		$(if $(OUTPUT),-o "$(OUTPUT)") \
		$(if $(VERBOSE),-v) \
		$(if $(FORCE),-f)

clean-meta:
	cd backend && PYTHONPATH=app/services $(PYTHON) app/services/metadata_cleaner.py \
		-p "$(AUDIO_PATH)" \
		$(ARGS)

extract-melody:
	cd backend && PYTHONPATH=app/services $(PYTHON) app/services/extract_melody_cli.py \
		"$(AUDIO)" \
		-o "$(MELODY_OUT)" \
		--fmin $(FMIN) \
		--fmax $(FMAX) \
		$(if $(MIN_NOTE_MS),--min-note-ms $(MIN_NOTE_MS)) \
		$(if $(NO_HPSS),--no-hpss) \
		$(if $(BPM),--bpm $(BPM)) \
		$(if $(KEY),--key $(KEY)) \
		$(if $(MODE),--mode $(MODE)) \
		$(if $(HARMONY),--harmony $(HARMONY))

# ── CLI — via Docker ───────────────────────────────────────────────────────────

docker-download:
	docker exec -it $(BACKEND_CONTAINER) \
		sh -c "cd /app && PYTHONPATH=app/services python app/services/downloader_cli.py \
			-s $(SOURCE) \
			$(if $(URL),-u '$(URL)') \
			$(if $(QUERY),-q '$(QUERY)') \
			--format $(FORMAT) \
			--bitrate $(BITRATE) \
			$(if $(OUTPUT),-o '$(OUTPUT)') \
			$(if $(VERBOSE),-v) \
			$(if $(FORCE),-f)"

docker-clean-meta:
	docker exec -it $(BACKEND_CONTAINER) \
		sh -c "cd /app && PYTHONPATH=app/services python app/services/metadata_cleaner.py \
			-p /app/media/$(MEDIA_PATH) \
			$(ARGS)"

docker-extract-melody:
	docker exec -it $(BACKEND_CONTAINER) \
		sh -c "cd /app && PYTHONPATH=app/services python app/services/extract_melody_cli.py \
			'/app/$(AUDIO)' \
			-o '/app/$(MELODY_OUT)' \
			--fmin $(FMIN) \
			--fmax $(FMAX) \
			$(if $(MIN_NOTE_MS),--min-note-ms $(MIN_NOTE_MS)) \
			$(if $(NO_HPSS),--no-hpss) \
			$(if $(BPM),--bpm $(BPM)) \
			$(if $(KEY),--key $(KEY)) \
			$(if $(MODE),--mode $(MODE)) \
			$(if $(HARMONY),--harmony $(HARMONY))"
