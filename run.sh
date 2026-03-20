#!/bin/bash
cd "$(dirname "$0")"

# Check for .env
if [ ! -f .env ]; then
  echo "⚠  No .env file found. Copy .env.example and add your ANTHROPIC_API_KEY."
  echo "   cp .env.example .env"
  exit 1
fi

# Install deps if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies…"
  pip install -r requirements.txt
fi

echo "Starting VC Job Agent at http://localhost:8000"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
