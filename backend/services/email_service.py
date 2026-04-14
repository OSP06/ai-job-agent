"""
email_service.py
────────────────
Gmail API (OAuth2) integration.

Creates Gmail DRAFTS — user reviews and sends manually.

First run: opens a browser for the Google OAuth consent flow.
Token is cached at settings.gmail_token_path for future runs.

Required scopes: https://www.googleapis.com/auth/gmail.compose
"""

import base64
import json
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.config import settings
from backend.utils.logger import logger

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

_service = None


def _get_service():
    global _service
    if _service:
        return _service

    creds: Optional[Credentials] = None
    token_path = Path(settings.gmail_token_path)
    creds_path = Path(settings.gmail_credentials_path)

    # Production path: token JSON supplied as env var (no browser OAuth possible on server)
    gmail_token_json = os.environ.get("GMAIL_TOKEN_JSON", "")
    if gmail_token_json:
        try:
            token_data = json.loads(gmail_token_json)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as e:
            logger.error(f"Failed to parse GMAIL_TOKEN_JSON env var: {e}")

    # Local path: read from file
    if not creds and token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Persist refreshed token back to file if possible
            if token_path.exists() or not gmail_token_json:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(creds.to_json())
        else:
            if not creds_path.exists():
                logger.warning(
                    "Gmail not configured. Run scripts/gmail_auth.py locally to get token.json, "
                    "then set GMAIL_TOKEN_JSON env var with its contents."
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
            logger.info(f"Gmail token saved to {token_path}")

    _service = build("gmail", "v1", credentials=creds)
    return _service


def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    sender: Optional[str] = None,
) -> Optional[str]:
    """
    Create a Gmail draft.

    Returns the draft ID string, or None if Gmail is not configured / creation fails.
    """
    service = _get_service()
    if not service:
        logger.info("Gmail not configured — draft skipped")
        return None

    from_addr = sender or settings.gmail_sender_email or "me"

    try:
        mime_msg = MIMEText(body, "plain")
        mime_msg["to"] = to
        mime_msg["from"] = from_addr
        mime_msg["subject"] = subject

        encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
        draft_body = {"message": {"raw": encoded}}

        draft = service.users().drafts().create(userId="me", body=draft_body).execute()
        draft_id = draft["id"]
        logger.info(f"Gmail draft created: {draft_id} → To: {to} | Subject: {subject}")
        return draft_id

    except HttpError as e:
        logger.error(f"Gmail API error creating draft: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating Gmail draft: {e}")
        return None
