"""
Gmail API client for fetching and reading emails.

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project, enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download as credentials/credentials.json
5. First run will open browser for OAuth consent
"""
import base64
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailClient:
    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None

    def authenticate(self):
        """Authenticate with Gmail API using OAuth2."""
        creds = None
        token_path = Path(self.token_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(self.credentials_file).exists():
                    raise FileNotFoundError(
                        f"Missing {self.credentials_file}. "
                        "Download OAuth credentials from Google Cloud Console. "
                        "See: https://console.cloud.google.com/apis/credentials"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)
        return self

    def fetch_emails(
        self,
        since: datetime | None = None,
        max_results: int = 100,
        query: str = "",
    ) -> list[dict]:
        """Fetch emails from Gmail, returning parsed metadata and snippets."""
        if not self.service:
            self.authenticate()

        q_parts = []
        if since:
            q_parts.append(f"after:{since.strftime('%Y/%m/%d')}")
        if query:
            q_parts.append(query)
        q = " ".join(q_parts) if q_parts else None

        results = (
            self.service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=q)
            .execute()
        )
        message_ids = results.get("messages", [])

        emails = []
        for msg_ref in message_ids:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )
            parsed = self._parse_message(msg)
            if parsed:
                emails.append(parsed)

        return emails

    def fetch_threads(
        self,
        since: datetime | None = None,
        max_results: int = 50,
    ) -> list[dict]:
        """Fetch email threads for richer context."""
        if not self.service:
            self.authenticate()

        q = f"after:{since.strftime('%Y/%m/%d')}" if since else None
        results = (
            self.service.users()
            .threads()
            .list(userId="me", maxResults=max_results, q=q)
            .execute()
        )
        thread_ids = results.get("threads", [])

        threads = []
        for t_ref in thread_ids:
            thread = (
                self.service.users()
                .threads()
                .get(userId="me", id=t_ref["id"], format="full")
                .execute()
            )
            messages = [
                self._parse_message(m) for m in thread.get("messages", [])
            ]
            messages = [m for m in messages if m]
            if messages:
                threads.append(
                    {
                        "thread_id": t_ref["id"],
                        "subject": messages[0].get("subject", ""),
                        "messages": messages,
                    }
                )
        return threads

    def send_email(self, to: str, subject: str, body_html: str, from_addr: str | None = None):
        """Send an email via Gmail API."""
        if not self.service:
            self.authenticate()

        from email.mime.text import MIMEText

        message = MIMEText(body_html, "html")
        message["to"] = to
        message["subject"] = subject
        if from_addr:
            message["from"] = from_addr

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        self.service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

    def _parse_message(self, msg: dict) -> dict | None:
        """Parse a Gmail API message into a clean dict."""
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        body = self._extract_body(msg.get("payload", {}))

        date_str = headers.get("date", "")
        try:
            parsed_date = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            parsed_date = date_str

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "sender": headers.get("from", ""),
            "recipients": self._parse_recipients(headers),
            "subject": headers.get("subject", "(no subject)"),
            "date": parsed_date,
            "body_snippet": body[:3000] if body else msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        """Extract text body from message payload, handling multipart."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        if payload.get("mimeType", "").startswith("multipart/"):
            for part in payload.get("parts", []):
                body = self._extract_body(part)
                if body:
                    return body

        if payload.get("body", {}).get("data"):
            text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            if payload.get("mimeType") == "text/html":
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
            return text

        return ""

    def _parse_recipients(self, headers: dict) -> list[str]:
        to = headers.get("to", "")
        cc = headers.get("cc", "")
        combined = f"{to}, {cc}" if cc else to
        return [addr.strip() for addr in combined.split(",") if addr.strip()]
