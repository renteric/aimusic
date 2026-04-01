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
        up down build rebuild logs restart ps \
        backend-shell frontend-shell \
        frontend-dev backend-dev \
        install-backend install-frontend \
        test lint \
        download clean-meta extract-melody \
        docker-download docker-clean-meta docker-extract-melody

# ── Help ───────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  Docker (production)"
	@echo "  ──────────────────────────────────────────────────────────"
	@echo "  make up                          Start all services (detached)"
	@echo "  make down                        Stop and remove containers"
	@echo "  make build                       Build Docker images"
	@echo "  make rebuild                     Rebuild from scratch, no cache"
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

up:
	@mkdir -p media data
	docker compose up -d

down:
	docker compose down

build:
	docker compose build \
		--build-arg USER_UID=$(shell id -u) \
		--build-arg USER_GID=$(shell id -g) \
		--build-arg USER_NAME=$(shell whoami)

rebuild:
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
