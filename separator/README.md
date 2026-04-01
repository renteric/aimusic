# Music Source Separator

AI-powered stem extraction. Upload any song and get individual tracks for
**vocals, drums, bass, guitar, piano/keys, and more** — 100% local, no cloud.

Powered by [Demucs](https://github.com/facebookresearch/demucs) (Meta AI Research) and [open-unmix](https://github.com/sigsep/open-unmix-pytorch).

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Web UI](#-web-ui)
  - [CLI Tool](#-cli-tool)
  - [Docker](#-docker)
  - [REST API](#-rest-api)
- [Available Models](#available-models)
- [Stems Reference](#stems-reference)
- [Performance](#performance)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Claude AI Development Setup](#claude-ai-development-setup)
  - [Agents](#agents)
  - [Slash Commands](#slash-commands-skills)
  - [Hooks](#hooks)
  - [Memory](#memory)
  - [Rules](#rules-claudemd)
- [Upgrading Models](#upgrading-models)
- [License](#license)

---

## Requirements

Configuration is managed via environment variables. Copy `.env.example` to `.env` and edit values like `MUSEP_API_PORT`, `MUSEP_JOBS`, or `MUSEP_DEVICE`. The same file is mounted into the container so behaviour stays consistent across environments.

### Native (developer mode)

- Ubuntu / Linux (tested on Ubuntu 22.04+)
- Python **3.12+**
- 32 GB RAM recommended
- 8-core CPU or better
- ~2 GB disk for model weights + dependencies
- `ffmpeg` installed and on PATH

### Docker (recommended for deployment)

- Docker Engine 24+
- Docker Compose v2+
- No GPU required — CPU mode works fine (5–15 min per song)

---

## Installation

```bash
bash scripts/setup.sh
```

This installs all Python dependencies, creates a virtual environment, and verifies that FFmpeg and Demucs are working correctly.

---

## Usage

### 🌐 Web UI

```bash
bash start.sh
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser, then:

1. Drag and drop your audio file
2. Select a model and which stems you want
3. Click **Separate Stems**
4. Preview and download individual stems or all at once as a ZIP

---

### 💻 CLI Tool

```bash
source venv/bin/activate

# Separate a single song (all stems)
python src/cli.py separate song.mp3

# Choose specific stems
python src/cli.py separate song.mp3 --stems vocals,drums,bass,guitar

# Choose model and output format
python src/cli.py separate song.mp3 --model htdemucs_6s --format wav --output ./my_stems

# Process an entire folder
python src/cli.py batch ./my_music_folder/ --stems vocals,guitar

# Inspect a file's metadata
python src/cli.py info song.mp3

# List available models
python src/cli.py models
```

---

### 🐳 Docker

A `Makefile` provides shortcuts (`make docker-build`, `make docker-up`, `make docker-down`).

```bash
# Build the image (required on first run or after dependency changes)
docker compose build

# Start the service in the background
docker compose up -d

# Tail logs
docker compose logs -f

# Stop
docker compose down
```

Browse to **[http://localhost:8000](http://localhost:8000)** — identical experience to native mode.

The Compose file mounts three host directories so data persists across restarts:

```yaml
volumes:
  - ./uploads:/app/uploads
  - ./outputs:/app/outputs
  - ./models:/app/models
```

---

### 🔌 REST API

```bash
source venv/bin/activate
python src/api.py
# Interactive docs: http://localhost:8000/docs
```

**Submit a separation job:**

```bash
curl -X POST "http://localhost:8000/api/separate" \
  -F "file=@song.mp3" \
  -F "model=htdemucs_6s" \
  -F "stems=vocals,drums"
# → {"job_id": "abc-123", "status": "pending"}
```

**Poll for status:**

```bash
curl http://localhost:8000/api/jobs/abc-123
# → {"status": "completed", "progress": 1.0, "stems": {...}}
```

**Download a single stem:**

```bash
curl -O http://localhost:8000/api/download/abc-123/vocals
```

**Download all stems as ZIP:**

```bash
curl -O http://localhost:8000/api/download/abc-123
```

**Other endpoints:**

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/health` | Server health and device info |
| GET | `/api/models` | List all available models |
| DELETE | `/api/jobs/{id}` | Delete a job and its files |
| GET | `/list` | Browse all output folders |
| GET | `/browse/{folder}` | Browse stems in a folder |

---

## Available Models

| Model | Stems | Quality | Speed |
| --- | --- | --- | --- |
| `htdemucs_6s` | vocals, drums, bass, guitar, piano, other | High | Medium |
| `htdemucs_ft` | vocals, drums, bass, other | Very High | Slow |
| `htdemucs` | vocals, drums, bass, other | Good | Fast |
| `mdx_extra` | vocals, drums, bass, other | High | Medium |
| `umx` | vocals, drums, bass, other | Good | Fast |
| `umxhq` | vocals, drums, bass, other | High | Medium |

> **Recommended:** `htdemucs_6s` — the only model that separates guitar and piano individually.
> **About `other`:** Captures everything not classified above — strings, flutes, brass, synths, orchestral instruments. It is the best available separation for those sources without custom training.

---

## Stems Reference

| Stem | What it captures |
| --- | --- |
| vocals | Lead vocals and background harmonies |
| drums | Full drum kit and percussion |
| bass | Bass guitar and sub-bass |
| guitar | Electric and acoustic guitar |
| piano | Piano, keyboards, organ |
| synthesizer | Synth pads and leads |
| strings | Violins, violas, cellos |
| woodwinds | Flute, clarinet, oboe, saxophone |
| brass | Trumpet, trombone, french horn |
| flute | Flute (targeted) |
| percussion | Non-kit percussion |
| other | Anything not covered above |

---

## Performance

Benchmarks on an 8-core CPU, 32 GB RAM:

| Song Length | `htdemucs_6s` | `htdemucs` |
| --- | --- | --- |
| 3 min | ~8–12 min | ~4–6 min |
| 5 min | ~15–20 min | ~8–10 min |
| 10 min | ~30–40 min | ~15–20 min |

**Tips:**

- Use `--model htdemucs` when you only need 4 stems
- Only select the stems you actually need
- Set `MUSEP_JOBS=1` if RAM is constrained

---

## Architecture

```mermaid
flowchart LR
    subgraph browser
      UI[Web UI / API client]
    end
    subgraph service[FastAPI service]
      UI -->|HTTP POST /api/separate| App[FastAPI app]
      App -->|background job| Queue((in-memory jobs))
      App -->|serves| Static[/static, /templates]
      Queue --> Separator[AudioSeparator / Demucs]
      Separator --> Outputs[outputs/ volume]
      App -->|downloads| Models[models/ volume]
    end
    classDef vol fill:#f9f,stroke:#333,stroke-width:1px;
    Outputs:::vol
    Models:::vol
    style UI fill:#eef,stroke:#333
```

**Request flow:**

```text
POST /api/separate
  → validate file (type, size)
  → save to uploads/{uuid}.ext
  → create Job (in-memory)
  → submit to ThreadPoolExecutor
  → return job_id immediately

Background thread:
  → AudioSeparator.separate()
      → ffmpeg: convert to 44100 Hz stereo WAV
      → demucs subprocess: extract stems
      → write stems to outputs/{song_name}_stems/
      → update job status & progress
```

---

## Project Structure

```text
separator/
├── CLAUDE.md                    # AI assistant rules (see below)
├── ARCHITECTURE.md              # design decisions
├── SECURITY.md                  # security hardening notes
├── README.md                    # this file
├── Makefile                     # Docker helpers
├── Dockerfile                   # multi-stage, non-root build
├── docker-compose.yml           # service definition
├── requirements.txt             # pinned Python dependencies
├── .env.example                 # configuration template
│
├── src/
│   ├── api.py                   # FastAPI app + security middleware
│   ├── cli.py                   # Click CLI with rich TUI
│   ├── config/
│   │   └── settings.py          # pydantic-settings config
│   ├── core/
│   │   └── separator.py         # AudioSeparator class
│   ├── static/                  # Vanilla JS + CSS
│   └── templates/               # Jinja2 HTML templates
│
├── .claude/                     # Claude Code AI configuration (see below)
│   ├── settings.json
│   ├── agents/
│   ├── commands/
│   └── memory/
│
├── uploads/                     # temporary incoming files (runtime)
├── outputs/                     # extracted stems by song (runtime)
├── models/                      # ML model weight cache (runtime)
├── files/                       # sample audio files for testing
└── scripts/
    └── setup.sh                 # bootstrap script
```

---

## Claude AI Development Setup

This project ships a complete [Claude Code](https://claude.ai/claude-code) configuration under `.claude/`. It gives Claude deep, project-specific knowledge across every session — no re-explaining the stack, security rules, or conventions.

```text
.claude/
├── settings.json        ← hooks and allowed commands
├── agents/              ← specialised sub-agents for domain tasks
│   ├── audio-debug.md
│   ├── api-tester.md
│   └── stem-reviewer.md
├── commands/            ← slash commands (reusable workflows)
│   ├── separate.md      → /separate
│   ├── lint.md          → /lint
│   ├── test-api.md      → /test-api
│   ├── check-outputs.md → /check-outputs
│   └── docker.md        → /docker
└── memory/              ← persistent project knowledge
    ├── MEMORY.md
    ├── architecture.md
    └── patterns.md
```

---

### Agents

Agents are specialised sub-processes Claude delegates to for domain-specific tasks. Invoke them by describing the problem — Claude routes to the right one automatically.

#### `audio-debug`

**When to use:** Any failure in the audio processing pipeline — FFmpeg errors, Demucs crashes, silent stems, corrupted output, model loading failures.

**What it knows:**

- The full pipeline from file upload → WAV conversion → Demucs subprocess → stem output
- Every common failure mode (missing FFmpeg, CUDA OOM, sample rate mismatch, wrong stem names)
- How to probe audio files with `ffprobe` and run Demucs in isolation for debugging
- Maps symptoms to root causes with concrete fix instructions

**Trigger examples:**

> "Why did separation fail for this file?"
> "The vocals stem is silent"
> "Demucs crashed with RuntimeError"

---

#### `api-tester`

**When to use:** Testing, validating, or exercising the FastAPI endpoints — after adding a new route, checking security headers, or verifying the full job lifecycle.

**What it knows:**

- Every endpoint in `src/api.py` with expected inputs and responses
- How to run smoke tests (health, models, security headers) without uploading a file
- The full job lifecycle: submit → poll → download stems → cleanup
- CORS validation (which origins should be allowed/blocked)
- Error case tests (invalid file type, non-existent job ID, oversized upload)

**Trigger examples:**

> "Test all API endpoints"
> "Verify the CORS headers are correct"
> "Run an end-to-end separation job against the local server"

---

#### `stem-reviewer`

**When to use:** Inspecting the `outputs/` directory after a separation run — checking completeness, file sizes, durations, or diagnosing missing/corrupt stems.

**What it knows:**

- Which stems each model can produce (e.g. `htdemucs_6s` gives guitar + piano; others do not)
- Quality indicators: expected duration match, minimum file size, silent stem detection
- Shell commands for batch inspection with `ffprobe`
- How to format a clean per-song report

**Trigger examples:**

> "Check what stems were extracted for Besame_mucho"
> "List all songs missing a vocals stem"
> "Are there any zero-byte stems in outputs/?"

---

### Slash Commands (Skills)

Slash commands are reusable, multi-step workflows invoked with `/command-name`. Claude executes them step by step, showing progress.

#### `/separate [file]`

Runs stem separation on an audio file via the CLI tool.

- Lists files in `files/` if no argument is given
- Confirms model, stems, and output format before running
- Shows extracted stems with file sizes and processing time

```bash
# Examples
/separate
/separate files/Besame_mucho.mp3
/separate files/Besame_mucho.mp3 --model htdemucs --stems vocals,drums
```

---

#### `/lint`

Auto-formats and lints all Python source files in `src/`.

1. **Black** — reformats to line length 88
2. **isort** — sorts imports (Black-compatible profile)
3. **flake8** — reports remaining style violations (`E203`, `W503` ignored)

Reports which files were changed and any remaining issues. Only Black and isort apply automatic fixes — flake8 violations are reported for manual review.

---

#### `/test-api`

Runs a smoke test suite against the local server at `http://localhost:8000`.

- Offers to start the server if it is not reachable
- Tests: `/health`, `/api/models`, `/list`, security headers
- Runs a full end-to-end job (submit → poll → download → cleanup) using `Besame_mucho.mp3`
- Prints a pass/fail summary table

---

#### `/check-outputs`

Inspects the `outputs/` directory and reports on all extracted stems.

- Lists all song directories and stems present
- Shows file sizes for each stem
- Flags zero-byte or suspiciously small files
- Checks audio durations on the most recently modified folder
- Reports total disk usage

---

#### `/docker [subcommand]`

Manages the Docker environment. Subcommands:

| Subcommand | Action |
| --- | --- |
| `up` | Start the service (`docker-compose up -d`) and tail logs |
| `down` | Stop the service |
| `build` | Rebuild the image (`--no-cache`) |
| `logs` | Tail live container logs |
| `shell` | Open a bash shell inside the running container |
| `status` | Show container status and health check result |

Defaults to `status` if no subcommand is given.

---

### Hooks

Hooks are shell commands that run automatically in response to Claude's tool calls. Defined in [`.claude/settings.json`](.claude/settings.json).

#### PostToolUse — Python formatting check

**Fires on:** Every file save (`Edit` or `Write` tool) that touches a `.py` file.

**What it does:** Runs `black --check` on the modified file and prints a warning if formatting is needed.

```text
⚠  Black: src/core/separator.py needs formatting — run: black src/core/separator.py
```

This does not auto-apply Black — it reminds you so you can run `/lint` deliberately.

---

#### PostToolUse — Docker rebuild reminder

**Fires on:** Every save to `Dockerfile` or `requirements.txt`.

**What it does:** Prints a reminder to rebuild the Docker image.

```text
⚠  Docker image may be stale — rebuild with: docker-compose build
```

Prevents the common mistake of editing dependencies and wondering why the container behaviour has not changed.

---

#### PreToolUse — Dangerous command guard

**Fires on:** Every `Bash` tool call, before execution.

**What it does:** Blocks commands matching destructive patterns and exits with code 2 (which prevents the command from running):

| Pattern | Reason |
| --- | --- |
| `rm -rf .../outputs\|uploads\|models` | Protects user data and model cache |
| `curl ... \| bash` | Prevents remote code execution |
| `wget ... \| sh` | Same as above |
| `DROP TABLE` | Prevents accidental DB destruction |

If blocked, Claude is told the reason and must find a safer alternative.

---

### Memory

Memory files in `.claude/memory/` are loaded into Claude's context at the start of every session. They give Claude stable, accurate knowledge about this project without you having to repeat yourself.

#### `MEMORY.md` — Session-loaded overview

Automatically loaded every session. Contains:

- What the project does and its tech stack
- Key file paths and their roles
- All available models and stem names
- Security posture summary
- Runtime behaviour (in-memory job store, device detection)
- All environment variables with their defaults

Keep this file under 200 lines — it is loaded on every conversation.

---

#### `architecture.md` — Deep technical reference

Detailed reference for when Claude needs to understand the system at depth. Contains:

- Full annotated request flow diagram (upload → separation → download)
- `AudioSeparator` class signature and all parameters
- Job state machine (`pending → processing → completed/failed`)
- All Pydantic response schemas for the API
- Configuration class relationships
- Frontend architecture (which JS file does what)
- Docker multi-stage build structure

---

#### `patterns.md` — Conventions and pitfalls

The "how we do things here" guide. Contains:

- Python style rules (Black 88, isort, flake8 flags, type hints)
- How to add a new FastAPI endpoint correctly
- How to add a new stem type (and what the model limitations are)
- The progress callback pattern used throughout the codebase
- Frontend `fetch()` pattern with error handling
- Template extension pattern
- Manual testing recipes (unit, CLI, API)
- Common pitfalls with explanations (in-memory job store, Demucs subprocess, FFmpeg PATH, model weight caching, stem availability per model)

---

### Rules (`CLAUDE.md`)

[`CLAUDE.md`](CLAUDE.md) is the project-level rule file. Claude reads it at the start of every session and must follow its instructions. It covers:

#### Coding standards

- **Black** (line length 88) + **isort** + **flake8** for all Python
- Type annotations required on all function signatures
- All config accessed via `settings.*` — no hardcoded values or paths

#### FastAPI conventions

- All user inputs validated at the API boundary (file type, size, job ID format)
- `HTTPException` for all error responses — never raw strings
- All new endpoints must go through the existing security middleware stack

#### Frontend rules

- No `<script>` blocks inside templates — JS lives in `src/static/`
- No `style="..."` attributes — CSS lives in `src/static/style.css`
- These are enforced by the Content-Security-Policy header; violations break the UI silently

#### Security non-negotiables

- CORS locked to localhost — do not widen it
- No `shell=True` in subprocess calls
- Job IDs sanitized before use in file paths (path traversal prevention)
- Non-root Docker user must not be changed
- CSP must not include `'unsafe-inline'` or `'unsafe-eval'`

#### Audio processing invariants

- Always convert input to 44100 Hz stereo WAV before passing to Demucs
- Demucs runs as a subprocess — capture stdout/stderr for progress
- `htdemucs_6s` does not natively produce woodwinds/brass/flute — those map to `other`

#### What not to do

- No database without a migration plan (jobs are currently in-memory by design)
- No npm or frontend build tools (zero-build frontend is intentional)
- No global exception handlers that swallow errors
- No secrets in `.env.example`
- No automated deletion of `outputs/`, `uploads/`, or `models/`

---

## Upgrading Models

For higher-quality separation, install `bs-roformer` with community weights from Hugging Face:

```bash
pip install bs-roformer
# Load weights from: huggingface.co/search?q=melband+roformer
```

See `docs/Music_Source_Separation_Technical_Proposal.docx` for the full research-grade setup guide.

---

## License

| Component | License |
| --- | --- |
| Project source code | MIT |
| Demucs models | MIT |
| MoisesDB training data | CC BY-NC-SA 4.0 (non-commercial only) |

---

Built with Demucs by Meta AI Research
