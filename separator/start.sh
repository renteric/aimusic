#!/bin/bash
# start.sh — Start the Music Separator API (local / non-Docker)
source venv/bin/activate 2>/dev/null || true

echo "Starting Music Source Separator API..."
echo "  API docs: http://localhost:8000/docs"
echo "  Health:   http://localhost:8000/health"
echo "  Press Ctrl+C to stop"
echo ""

uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
