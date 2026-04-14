#!/usr/bin/env bash
# run_agent.sh — Start the AI Job Agent backend
set -e

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  echo "❌ Virtual environment not found. Run ./scripts/setup_env.sh first."
  exit 1
fi

# Check .env exists
if [ ! -f ".env" ]; then
  echo "❌ .env not found. Run ./scripts/setup_env.sh first."
  exit 1
fi

# Ensure required dirs exist
mkdir -p backend/resumes backend/storage logs

echo ""
echo "🤖  AI Job Agent starting..."
echo "    API:  http://localhost:8000"
echo "    Docs: http://localhost:8000/docs"
echo ""

uvicorn backend.main:app --host 0.0.0.0 --port 8000
