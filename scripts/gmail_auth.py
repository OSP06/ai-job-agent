#!/usr/bin/env python3
"""
gmail_auth.py — Run OAuth2 flow locally to get a Gmail token for deployment.

Usage:
  1. Download credentials.json from Google Cloud Console (OAuth2 Desktop app)
     and place it at backend/credentials.json
  2. Run: python scripts/gmail_auth.py
  3. Complete the browser consent screen
  4. Copy the printed JSON and set it as GMAIL_TOKEN_JSON in Railway env vars

You only need to do this once. The refresh token is long-lived.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
CREDS_PATH = Path("backend/credentials.json")
TOKEN_PATH = Path("backend/token.json")


def main():
    if not CREDS_PATH.exists():
        print(f"ERROR: {CREDS_PATH} not found.")
        print("Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

    token_json = creds.to_json()
    print("\n" + "=" * 60)
    print("SUCCESS! Gmail token obtained.")
    print("=" * 60)
    print("\nSet this as the GMAIL_TOKEN_JSON environment variable in Railway:\n")
    print(token_json)
    print("\n" + "=" * 60)
    print(f"Token also saved locally to: {TOKEN_PATH}")


if __name__ == "__main__":
    main()
