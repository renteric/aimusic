# 📋 Project Overview & Architecture

## Quick Reference

### Project Structure
```
separator/
├── Dockerfile              # Production-ready, multi-stage build
├── docker-compose.yml      # Orchestration with volumes
├── requirements.txt        # Python dependencies (pinned versions)
├── SECURITY.md             # Comprehensive security documentation
├── README.md               # User-facing documentation
├── CLAUDE.md               # AI assistant instructions
│
├── src/
│   ├── api.py              # FastAPI REST API + security middleware
│   ├── cli.py              # Command-line interface
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py     # Configuration: paths, models, defaults
│   ├── core/
│   │   ├── __init__.py
│   │   └── separator.py    # Audio processing logic (Demucs wrapper)
│   ├── static/
│   │   ├── style.css       # Global styles (no inline styles)
│   │   ├── index.js        # Upload & job management
│   │   ├── browse.js       # Stem browser & playback
│   │   └── player.js       # Audio player (legacy)
│   └── templates/
│       ├── index.html      # Upload interface
│       ├── browse.html     # Stem browser with controls
│       ├── list.html       # All extracted stems
│       └── player.html     # Player page (legacy)
│
├── uploads/ (runtime)      # Temporary audio files
├── outputs/                # Extracted stems directory
└── models/                 # Pretrained Demucs models
```

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Runtime** | Python | 3.13 |
| **Web Framework** | FastAPI | Latest |
| **Server** | Uvicorn | Latest |
| **Audio Processing** | Demucs | Latest |
| **Neural Network** | PyTorch+Torchaudio | 2.10.0+cpu (CPU wheels) |
| **Frontend** | Vanilla HTML5/CSS/JS | ES6+ |
| **Containerization** | Docker | 25.0+ |
| **Audio Codec** | FFmpeg | 6.0+ |

---

## API Endpoints

### Audio Separation
```
POST /api/separate
  - Query params: model, stems
  - Body: multipart/form-data (audio file)
  - Returns: { job_id, status, progress }
```

### Job Status
```
GET /api/jobs/{job_id}
  - Returns: { status, progress, message, stems_produced, error }
```

### Download
```
GET /api/download/{job_id}/{stem}         # Download single stem
GET /api/download/{job_id}                # Download all as ZIP
```

### Browse
```
GET /list                                 # List all extracted folders
GET /browse/{folder}                      # Browse folder stems
GET /api/stems/{folder}                   # Get stems for folder (JSON)
```

### Health
```
GET /health                               # Health check + device info
GET /api/models                           # List available models
```

---

## Security Architecture

### Defense Layers (Onion Model)
```
Layer 1 (Network):
  └─ TrustedHostMiddleware: Only localhost

Layer 2 (Protocol):
  └─ CORS Whitelist: localhost only
  └─ HTTPS ready: upgrade-insecure-requests

Layer 3 (Headers):
  └─ CSP: No inline scripts/styles
  └─ X-Content-Type-Options: nosniff
  └─ X-Frame-Options DENY: Prevent clickjacking

Layer 4 (Application):
  └─ Jinja2 auto-escaping: XSS prevention
  └─ Input validation: Pydantic models
  └─ Event listeners: No onclick handlers

Layer 5 (Container):
  └─ Non-root user: UID 1000
  └─ Minimal image: Production dependencies only
  └─ Read-only app code: No runtime modifications
```

---

## Development Workflow

### 1. Setup
```bash
cd /home/rik/dev/mystudio/separator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Locally
```bash
# Terminal 1: FastAPI
uvicorn src.api:app --reload --port 8000

# Terminal 2: Access UI
open http://localhost:8000
```

### 3. Docker Build & Run
```bash
# Build
docker build -t separator:latest .

# Run with volumes
docker run -p 8000:8000 \
  -v $(pwd)/outputs:/app/outputs \
  -v $(pwd)/models:/app/models \
  separator:latest
```

### 4. Make Changes
- **HTML/CSS/JS changes:** Auto-reload (no restart needed)
- **Python changes:** Restart `uvicorn src.api:app --reload`
- **Dependencies:** Run `pip install` and rebuild Docker

---

## File Organization Principles

### src/api.py
- **Purpose:** REST API + security middleware
- **Size:** ~500-700 lines
- **Sections:**
  - Imports & logging
  - Security middleware setup
  - Pydantic models (types)
  - In-memory job store
  - Helper functions
  - Route handlers
  - Background tasks

### src/core/separator.py
- **Purpose:** Demucs audio processing wrapper
- **Handles:**
  - Model loading
  - Audio inference
  - Format conversion
  - Progress callbacks

### src/config/settings.py
- **Purpose:** Configuration & constants
- **Contains:**
  - Paths (BASE_DIR, uploads_dir, etc.)
  - Model definitions
  - Stem groups
  - Default parameters

### src/static/style.css
- **Scope:** Global styles for ALL pages
- **Structure:**
  - CSS variables for theming
  - Layout & components
  - Responsive media queries
  - Animations & transitions
  - No page-specific overrides

### src/static/*.js
- **index.js:** Upload UI + job polling
- **browse.js:** Playback controls + pitch shifting
- **player.js:** Legacy player (simpler interface)

### src/templates/*.html
- **Structure:** Minimal, no inline styling
- **Scripts:** External JS with defer attribute
- **Data:** Passed via `<script type="application/json">`
- **Styling:** CSS link in `<head>`

---

## Key Design Decisions

### 1. **No Inline CSS/JS**
- Enables strict CSP
- Easier to maintain
- Better caching (separate files)
- Prevents accidental XSS

### 2. **Vanilla JS (No Framework)**
- Smaller payload
- No dependency vulnerabilities
- Direct DOM control
- Clear performance characteristics

### 3. **Job-Based Architecture**
- Async separation (non-blocking)
- Status polling (client-side)
- Resumable downloads
- Browser-safe (works with back button)

### 4. **Song-Name Organization**
- Output structure: `/outputs/song_name/stem.mp3`
- Replaces: `/outputs/job_id/stem.mp3`
- User-friendly browsing
- Easy backup & sharing

### 5. **Multi-Stage Docker**
- Smaller final image (~2GB → ~1.2GB with PyTorch)
- Production-ready
- Security: no build tools in runtime

---

## Testing & Validation

### Security Testing
```bash
# CSP violations
curl -I http://localhost:8000/ | grep -i "Content-Security"

# CORS rejection
curl -H "Origin: http://evil.com" -I http://localhost:8000/

# Headers check
curl -I http://localhost:8000/ | grep -E "X-|Referrer|Permissions"
```

### Functional Testing
```bash
# Upload audio
curl -F "file=@test.mp3" http://localhost:8000/api/separate?model=htdemucs&stems=vocals,drums

# Check job status
curl http://localhost:8000/api/jobs/{job_id}

# List stems
curl http://localhost:8000/list
```

---

## Common Tasks

### Add New Audio Format Support
1. Edit `requirements.txt` (ensure FFmpeg installed)
2. Test format in `src/core/separator.py`
3. Update upload dialog `accept=""` in `index.html`

### Adjust CSP Policy
1. Edit `SecurityHeadersMiddleware` in `src/api.py`
2. Test in browser console for CSP violations
3. Update SECURITY.md documentation

### Add New Stem Group
1. Add to `STEM_GROUPS` in `src/config/settings.py`
2. Add color & label in `src/static/index.js`
3. Update model compatibility in `api.py`

### Customize Theming
1. Edit CSS variables in `src/static/style.css`
2. Update all `:root { --color: ... }` values
3. Test across all templates

---

## Performance Notes

### Browser Performance
- CSS file: ~40KB (gzipped: ~8KB)
- index.js: ~10KB (gzipped: ~3KB)
- browse.js: ~5KB (gzipped: ~2KB)
- player.js: ~3KB (gzipped: ~1KB)
- **Total:** <20KB gzipped

### Server Performance
- Audio processing: GPU-accelerated (if available)
- CPU fallback: ~5-15 min per song
- Memory: ~2-3GB during inference
- Disk: ~200MB per WAV, ~40MB per MP3

### Optimization Opportunities
1. Add Service Worker for offline caching
2. Implement WebWorker for UI responsiveness
3. Stream large file transfers
4. Add database for persistent job history

---

## Maintenance Checklist

### Weekly
- [ ] Check application logs for errors
- [ ] Verify audio quality of separated stems
- [ ] Test file upload functionality

### Monthly
- [ ] Run `pip audit` for security vulnerabilities
- [ ] Update README with latest features
- [ ] Clean up old temporary files in `/uploads`
- [ ] Monitor disk usage in `/outputs`

### Quarterly
- [ ] Security audit (re-run OWASP checks)
- [ ] Dependencies update check
- [ ] Performance profiling
- [ ] Docker image size analysis

---

## Troubleshooting

### Audio File Not Processing
```
Check:
1. File format is supported (MP3, WAV, FLAC, OGG, M4A, AAC)
2. File size < 200MB
3. FFmpeg is installed and working
4. Check /uploads directory for stuck files
```

### Stems Sound Distorted
```
Possible causes:
1. Source audio is already heavily compressed
2. Model quality vs input quality mismatch
3. Audio loudness too high (peaks clipping)
Solution: Try different model or normalize audio first
```

### Out of Memory During Processing
```
Solutions:
1. Add more RAM to container
2. Reduce audio file size
3. Use CPU mode (slower but more memory-efficient)
4. Process shorter segments separately
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-10 | Security hardening: CSP, external JS/CSS, Docker improvements |
| 0.9.0 | 2026-03-09 | Added stem browser with timeline & pitch controls |
| 0.8.0 | 2026-03-08 | Song-based file organization |
| 0.7.0 | 2026-03-07 | Multiple model support |
| 0.6.0 | 2026-02-28 | Docker containerization |

---

*Last Updated: March 10, 2026*
*Maintainer: Development Team*
*License: See LICENSE file*
