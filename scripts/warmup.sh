#!/usr/bin/env bash
# warmup.sh — Run ONCE after setup to pre-scan all C extensions.
# macOS security-scans every new .so file on first load (takes ~100s per file).
# This script triggers all those scans up front so future startups are instant.

set -e
source .venv/bin/activate

echo ""
echo "⏳  Pre-scanning C extensions for macOS security approval."
echo "    This runs ONCE and may take 5–15 minutes."
echo "    Future startups will be instant."
echo ""

python3 - << 'EOF'
import sys, time
sys.path.insert(0, '.')

libs = [
    ("pydantic",            "import pydantic"),
    ("pydantic_settings",   "import pydantic_settings"),
    ("sqlalchemy",          "import sqlalchemy"),
    ("fastapi",             "import fastapi"),
    ("uvicorn",             "import uvicorn"),
    ("anthropic",           "import anthropic"),
    ("openai",              "import openai"),
    ("httpx",               "import httpx"),
    ("google.auth",         "import google.auth"),
    ("googleapiclient",     "import googleapiclient.discovery"),
    ("apscheduler",         "import apscheduler"),
    ("loguru",              "from loguru import logger"),
    ("numpy",               "import numpy"),
    ("scipy (via st)",      "import scipy"),
]

total = time.time()
for name, stmt in libs:
    t = time.time()
    sys.stdout.write(f"  scanning {name}... ")
    sys.stdout.flush()
    try:
        exec(stmt)
        elapsed = time.time() - t
        print(f"✓  ({elapsed:.1f}s)")
    except Exception as e:
        print(f"skip ({e})")

print(f"\n✅  All done in {time.time()-total:.0f}s. Future startups will be fast.\n")
EOF
