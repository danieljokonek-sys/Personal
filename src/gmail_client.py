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

# Gmail read/send/modify + Calendar read — all three accounts need these
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GmailClient:
    def __init__(self, credentials_file: str, token_file: str, account_email: str = ""):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.account_email = account_email   # hint shown during OAuth flow
        self.service = None
        self._creds = None
        self._label_cache: dict[str, str] = {}  # name → label_id

    def authenticate(self):
        """Authenticate this account via OAuth2. Opens browser on first run."""
        creds = None
        token_path = Path(self.token_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            # If scopes changed, force re-auth
            if creds and creds.scopes and not all(s in creds.scopes for s in SCOPES):
                creds = None

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

    def fetch_sent_emails(
        self,
        since: datetime | None = None,
        max_results: int = 40,
    ) -> list[dict]:
        """Fetch recently sent emails for follow-up detection."""
        if not self.service:
            self.authenticate()
        q_parts = ["in:sent"]
        if since:
            q_parts.append(f"after:{since.strftime('%Y/%m/%d')}")
        results = self.service.users().messages().list(
            userId="me", q=" ".join(q_parts), maxResults=max_results
        ).execute()
        emails = []
        for msg_ref in results.get("messages", []):
            msg = self.service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            parsed = self._parse_message_metadata(msg)
            if parsed:
                emails.append(parsed)
        return emails

    def get_thread_messages(self, thread_id: str) -> list[dict]:
        """Get all messages in a thread (metadata only) for reply detection."""
        if not self.service:
            self.authenticate()
        thread = self.service.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        return [
            m for m in
            (self._parse_message_metadata(msg) for msg in thread.get("messages", []))
            if m
        ]

    def get_or_create_label(self, name: str, color: dict | None = None) -> str:
        """Return Gmail label ID for the given name, creating it if needed.

        Args:
            name: Label display name.
            color: Optional dict with 'textColor' and 'backgroundColor'
                   using Gmail's allowed hex values.
        """
        if name in self._label_cache:
            return self._label_cache[name]
        if not self.service:
            self.authenticate()
        result = self.service.users().labels().list(userId="me").execute()
        for label in result.get("labels", []):
            if label["name"].lower() == name.lower():
                self._label_cache[name] = label["id"]
                # Apply color to existing label if provided and not already set
                if color and not label.get("color"):
                    try:
                        self.service.users().labels().update(
                            userId="me", id=label["id"],
                            body={"color": color},
                        ).execute()
                    except Exception:
                        pass
                return label["id"]
        # Create it
        body: dict = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        if color:
            body["color"] = color
        try:
            new_label = self.service.users().labels().create(
                userId="me", body=body,
            ).execute()
        except Exception:
            # Color might be invalid — retry without color
            body.pop("color", None)
            new_label = self.service.users().labels().create(
                userId="me", body=body,
            ).execute()
        self._label_cache[name] = new_label["id"]
        return new_label["id"]

    def apply_label(self, message_id: str, label_id: str):
        """Add a label to a Gmail message."""
        if not self.service:
            self.authenticate()
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()

    def apply_labels_and_actions(
        self,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ):
        """Modify labels on a message — used for labeling, archiving, etc.

        Archiving = remove 'INBOX' label.
        """
        if not self.service:
            self.authenticate()
        body: dict = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids
        if body:
            self.service.users().messages().modify(
                userId="me", id=message_id, body=body
            ).execute()

    def list_labels(self) -> list[dict]:
        """Return all labels (system + user) for this account."""
        if not self.service:
            self.authenticate()
        result = self.service.users().labels().list(userId="me").execute()
        return result.get("labels", [])

    def get_messages_by_label(
        self, label_id: str, max_results: int = 500
    ) -> list[str]:
        """Return message IDs that carry a given label."""
        if not self.service:
            self.authenticate()
        ids: list[str] = []
        page_token = None
        while True:
            kwargs: dict = {
                "userId": "me",
                "labelIds": [label_id],
                "maxResults": min(max_results - len(ids), 500),
            }
            if page_token:
                kwargs["pageToken"] = page_token
            result = self.service.users().messages().list(**kwargs).execute()
            for msg in result.get("messages", []):
                ids.append(msg["id"])
            page_token = result.get("nextPageToken")
            if not page_token or len(ids) >= max_results:
                break
        return ids

    def delete_label(self, label_id: str):
        """Permanently delete a user label (does NOT delete the messages)."""
        if not self.service:
            self.authenticate()
        self.service.users().labels().delete(userId="me", id=label_id).execute()

    def archive_email(self, message_id: str):
        """Archive a message (remove from INBOX)."""
        self.apply_labels_and_actions(message_id, remove_label_ids=["INBOX"])

    def trash_email(self, message_id: str):
        """Move a message to trash."""
        if not self.service:
            self.authenticate()
        self.service.users().messages().trash(userId="me", id=message_id).execute()

    def fetch_inbox_emails(
        self,
        max_results: int = 100,
        page_token: str | None = None,
        extra_query: str = "",
    ) -> tuple[list[dict], str | None]:
        """Fetch emails from the INBOX, returning (emails, next_page_token).

        Used by the organizer to page through the current inbox.
        """
        return self._fetch_emails_paged(
            base_query="in:inbox", max_results=max_results,
            page_token=page_token, extra_query=extra_query,
        )

    def fetch_all_emails_paged(
        self,
        max_results: int = 100,
        page_token: str | None = None,
        extra_query: str = "",
    ) -> tuple[list[dict], str | None]:
        """Fetch ALL emails (not just inbox), returning (emails, next_page_token).

        Used by the organizer for comprehensive historical deep-clean.
        Excludes sent, drafts, spam, and trash by default.
        """
        return self._fetch_emails_paged(
            base_query="-in:sent -in:drafts -in:spam -in:trash",
            max_results=max_results, page_token=page_token,
            extra_query=extra_query,
        )

    def _fetch_emails_paged(
        self,
        base_query: str,
        max_results: int = 100,
        page_token: str | None = None,
        extra_query: str = "",
    ) -> tuple[list[dict], str | None]:
        """Internal: fetch a page of emails matching a query."""
        if not self.service:
            self.authenticate()

        q = base_query
        if extra_query:
            q += f" {extra_query}"

        kwargs: dict = {"userId": "me", "maxResults": max_results, "q": q}
        if page_token:
            kwargs["pageToken"] = page_token

        results = self.service.users().messages().list(**kwargs).execute()
        message_ids = results.get("messages", [])
        next_token = results.get("nextPageToken")

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

        return emails, next_token

    def _parse_message_metadata(self, msg: dict) -> dict | None:
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        date_str = headers.get("date", "")
        try:
            parsed_date = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            parsed_date = date_str
        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "sender": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "date": parsed_date,
            "labels": msg.get("labelIds", []),
        }

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
