"""
Gmail API client — supports multiple accounts, each with its own token file.

All accounts share one credentials.json (OAuth client), but get separate
token files so you stay signed in to all three simultaneously.

Scopes cover Gmail (read + send) and Calendar (read).
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

# Gmail read/send + Calendar read — all three accounts need these
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GmailClient:
    def __init__(self, credentials_file: str, token_file: str, account_email: str = ""):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.account_email = account_email   # hint shown during OAuth flow
        self.service = None
        self._creds = None

    def authenticate(self):
        """Authenticate this account via OAuth2. Opens browser on first run."""
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
                        f"Missing {self.credentials_file}.\n"
                        "Download OAuth credentials from Google Cloud Console:\n"
                        "  APIs & Services → Credentials → Create → OAuth 2.0 Client ID → Desktop app\n"
                        "Save the downloaded file as credentials/credentials.json"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                hint = f" for {self.account_email}" if self.account_email else ""
                print(f"\nOpening browser to authorize Gmail access{hint}...")
                print("Sign in with the correct Google account when prompted.\n")
                creds = flow.run_local_server(port=0, login_hint=self.account_email or None)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())

        self._creds = creds
        self.service = build("gmail", "v1", credentials=creds)
        return self

    def get_credentials(self):
        """Return raw credentials (used by CalendarClient for the same account)."""
        if not self._creds:
            self.authenticate()
        return self._creds

    def fetch_emails(
        self,
        since: datetime | None = None,
        max_results: int = 100,
        extra_query: str = "",
    ) -> list[dict]:
        """Fetch emails from this Gmail account since the given datetime."""
        if not self.service:
            self.authenticate()

        q_parts = []
        if since:
            q_parts.append(f"after:{since.strftime('%Y/%m/%d')}")
        if extra_query:
            q_parts.append(extra_query)
        q = " ".join(q_parts) if q_parts else None

        kwargs = {"userId": "me", "maxResults": max_results}
        if q:
            kwargs["q"] = q

        results = self.service.users().messages().list(**kwargs).execute()
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

    def send_email(self, to: str, subject: str, body_html: str):
        """Send an email from this account."""
        if not self.service:
            self.authenticate()

        from email.mime.text import MIMEText
        message = MIMEText(body_html, "html")
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        self.service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

    def _parse_message(self, msg: dict) -> dict | None:
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
            "account_email": self.account_email,
            "sender": headers.get("from", ""),
            "recipients": self._parse_recipients(headers),
            "subject": headers.get("subject", "(no subject)"),
            "date": parsed_date,
            "body_snippet": body[:3000] if body else msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
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


def build_clients(config: dict) -> list[GmailClient]:
    """Build one GmailClient per configured account."""
    creds_file = config.get("google", {}).get(
        "credentials_file", "credentials/credentials.json"
    )
    clients = []
    for account in config.get("accounts", []):
        clients.append(
            GmailClient(
                credentials_file=creds_file,
                token_file=account["token_file"],
                account_email=account["email"],
            )
        )
    return clients


def get_send_client(config: dict, clients: list[GmailClient]) -> GmailClient:
    """Return the GmailClient that should send digest emails."""
    send_from = config.get("digest", {}).get("send_from_account", "Personal")
    accounts = config.get("accounts", [])
    for i, acct in enumerate(accounts):
        if acct["name"] == send_from:
            return clients[i]
    return clients[0]
