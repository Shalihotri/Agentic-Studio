import base64
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import Settings
from app.models import EmailExecutionResult

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _build_oauth_flow(self) -> InstalledAppFlow:
        if self._settings.gmail_credentials_file.exists():
            return InstalledAppFlow.from_client_secrets_file(
                str(self._settings.gmail_credentials_file),
                GMAIL_SCOPES,
            )

        if self._settings.gmail_client_id and self._settings.gmail_client_secret:
            client_config = {
                "installed": {
                    "client_id": self._settings.gmail_client_id,
                    "client_secret": self._settings.gmail_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            return InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)

        raise ValueError(
            "Gmail OAuth configuration missing. Provide GMAIL_CREDENTIALS_FILE or both "
            "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET."
        )

    def _get_credentials(self) -> Credentials:
        creds: Credentials | None = None
        if self._settings.gmail_token_file.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._settings.gmail_token_file),
                GMAIL_SCOPES,
            )

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = self._build_oauth_flow()
            creds = flow.run_local_server(port=0)

        self._settings.gmail_token_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings.gmail_token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def _build_service(self):
        return build("gmail", "v1", credentials=self._get_credentials())

    @staticmethod
    def _encode_message(message: EmailMessage) -> str:
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return raw

    def _compose_message(
        self,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        reply_to_message_id: str | None,
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._settings.gmail_sender_email
        if to:
            message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)
        message["Subject"] = subject
        if reply_to_message_id:
            message["In-Reply-To"] = reply_to_message_id
            message["References"] = reply_to_message_id
        message.set_content(body)
        return message

    def send_message(
        self,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        thread_id: str | None,
        reply_to_message_id: str | None,
    ) -> EmailExecutionResult:
        service = self._build_service()
        message = self._compose_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
            reply_to_message_id=reply_to_message_id,
        )
        payload = {"raw": self._encode_message(message)}
        if thread_id:
            payload["threadId"] = thread_id
        result = service.users().messages().send(userId="me", body=payload).execute()
        return EmailExecutionResult(
            action="send",
            message_id=result.get("id"),
            thread_id=result.get("threadId"),
            status="sent",
        )

    def create_draft(
        self,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        thread_id: str | None,
        reply_to_message_id: str | None,
    ) -> EmailExecutionResult:
        service = self._build_service()
        message = self._compose_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
            reply_to_message_id=reply_to_message_id,
        )
        payload = {"message": {"raw": self._encode_message(message)}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        result = service.users().drafts().create(userId="me", body=payload).execute()
        return EmailExecutionResult(
            action="draft",
            draft_id=result.get("id"),
            thread_id=result.get("message", {}).get("threadId"),
            status="drafted",
        )

    def reply_message(
        self,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        thread_id: str | None,
        reply_to_message_id: str | None,
    ) -> EmailExecutionResult:
        return self.send_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
        )
