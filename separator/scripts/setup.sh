#!/bin/bash
# scripts/setup.sh — One-shot setup for Ubuntu/Linux
# Run: bash scripts/setup.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║   🎵  Music Source Separator — Setup        ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. System dependencies ──────────────────────────────────────────────────
echo -e "${YELLOW}[1/5] Installing system dependencies...${NC}"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    ffmpeg \
    libsndfile1 \
    python3-pip \
    python3-venv \
    curl \
    git

echo -e "${GREEN}✓ System dependencies installed${NC}"

# ── 2. Python virtual environment ──────────────────────────────────────────
echo -e "${YELLOW}[2/5] Creating Python virtual environment...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip --quiet
echo -e "${GREEN}✓ Virtual environment ready (./venv)${NC}"

# ── 3. Python packages ──────────────────────────────────────────────────────
echo -e "${YELLOW}[3/5] Installing Python packages...${NC}"
echo "    This may take a few minutes (PyTorch is large)..."

# Install PyTorch CPU version (lighter, suitable for laptop)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet

# Install remaining packages
pip install -r requirements.txt --quiet

echo -e "${GREEN}✓ Python packages installed${NC}"

# ── 4. Create directories ──────────────────────────────────────────────────
echo -e "${YELLOW}[4/5] Creating project directories...${NC}"
mkdir -p models uploads outputs

echo -e "${GREEN}✓ Directories created${NC}"

# ── 5. Pre-download Demucs model ──────────────────────────────────────────
echo -e "${YELLOW}[5/5] Pre-downloading htdemucs_6s model (~85MB)...${NC}"
echo "    This runs a quick silent test to trigger model download."
python3 -c "
import subprocess, sys
result = subprocess.run(
    ['python', '-m', 'demucs', '--help'],
    capture_output=True
)
if result.returncode == 0:
    print('  Demucs available ✓')
else:
    print('  Warning: demucs check failed', file=sys.stderr)
"
echo -e "${GREEN}✓ Model will download automatically on first use${NC}"

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗"
echo -e "║   ✅  Setup Complete!                        ║"
echo -e "╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Activate environment:  ${YELLOW}source venv/bin/activate${NC}"
echo ""
echo -e "Start the Web UI:      ${GREEN}python src/api.py${NC}"
echo -e "                       Then open: http://localhost:8000"
echo ""
echo -e "Use the CLI:           ${GREEN}python src/cli.py separate song.mp3${NC}"
echo -e "                       ${GREEN}python src/cli.py models${NC}"
echo -e "                       ${GREEN}python src/cli.py batch ./my_songs/${NC}"
echo ""
echo -e "${YELLOW}⚡ CPU mode — each song takes ~5–15 min. Be patient!${NC}"
