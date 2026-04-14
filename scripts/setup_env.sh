#!/usr/bin/env bash
# setup_env.sh — First-time project setup
set -e

echo "──────────────────────────────────────────"
echo "  AI Job Agent — Environment Setup"
echo "──────────────────────────────────────────"

# 1. Create virtual environment
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv .venv
fi

# 2. Activate
source .venv/bin/activate
echo "→ Virtual environment active: $(python --version)"

# 3. Install dependencies
echo "→ Installing dependencies (this may take a few minutes)..."
pip install --upgrade pip -q
pip install -r requirements.txt

# 4. Copy .env if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  .env created from template. Fill in your API keys:"
  echo "    ANTHROPIC_API_KEY  — https://console.anthropic.com"
  echo "    OPENAI_API_KEY     — https://platform.openai.com"
  echo "    GMAIL_CREDENTIALS  — Google Cloud Console (optional)"
  echo "    HUNTER_API_KEY     — https://hunter.io (optional)"
else
  echo "→ .env already exists (skipped)"
fi

# 5. Create required directories
mkdir -p backend/resumes backend/storage logs

# 6. Check for resumes
PDF_COUNT=$(ls backend/resumes/*.pdf 2>/dev/null | wc -l | tr -d ' ')
if [ "$PDF_COUNT" -eq "0" ]; then
  echo ""
  echo "⚠️  No resumes found. Add PDF files to backend/resumes/"
  echo "    Example names: backend_resume.pdf, ai_resume.pdf"
else
  echo "→ Found ${PDF_COUNT} resume(s) in backend/resumes/"
fi

echo ""
echo "✅  Setup complete. Run the agent with:"
echo "    ./scripts/run_agent.sh"
echo ""
