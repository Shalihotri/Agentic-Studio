from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

from app.config import Settings
from app.models import EmailExecutionResult


class OutlookClient:
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _get_token_url(self) -> str:
        auth_url = self._settings.outlook_auth_url.strip()
        if not auth_url:
            raise ValueError("Outlook OAuth configuration missing. Set OUTLOOK_AUTH_URL.")
        if auth_url.endswith("/authorize"):
            return auth_url[: -len("/authorize")] + "/token"
        return auth_url.rstrip("/") + "/token"

    def _get_access_token(self) -> str:
        if not self._settings.outlook_client_id or not self._settings.outlook_client_secret:
            raise ValueError(
                "Outlook OAuth configuration missing. Set OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET."
            )

        response = requests.post(
            self._get_token_url(),
            data={
                "client_id": self._settings.outlook_client_id,
                "client_secret": self._settings.outlook_client_secret,
                "scope": "https://graph.microsoft.com/" + self._settings.outlook_scope.lstrip("/"),
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ValueError("Outlook token response did not include an access token.")
        return str(token)

    def _get_sender_email(self) -> str:
        sender = self._settings.outlook_sender_email.strip()
        if not sender:
            env_path = Path(__file__).resolve().parents[1] / ".env"
            env_values = dotenv_values(env_path)
            sender = str(env_values.get("OUTLOOK_SENDER_EMAIL") or "").strip()
        if not sender:
            raise ValueError(
                "Outlook sender email missing. Set OUTLOOK_SENDER_EMAIL in app/.env."
            )
        return sender

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if response.ok:
            return
        try:
            payload = response.json()
            error = payload.get("error", {})
            code = error.get("code") or response.status_code
            message = error.get("message") or response.text
            raise ValueError(f"Microsoft Graph error [{code}]: {message}")
        except ValueError:
            raise
        except Exception:
            response.raise_for_status()

    def _build_message(
        self,
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        reply_to_message_id: str | None,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body,
            },
            "toRecipients": [
                {"emailAddress": {"address": address}} for address in to if address
            ],
            "ccRecipients": [
                {"emailAddress": {"address": address}} for address in cc if address
            ],
            "bccRecipients": [
                {"emailAddress": {"address": address}} for address in bcc if address
            ],
        }
        if reply_to_message_id:
            message["internetMessageHeaders"] = [
                {"name": "In-Reply-To", "value": reply_to_message_id},
                {"name": "References", "value": reply_to_message_id},
            ]
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
        sender = self._get_sender_email()
        response = requests.post(
            f"{self.GRAPH_BASE_URL}/users/{sender}/sendMail",
            headers=self._build_headers(),
            json={
                "message": self._build_message(
                    to=to,
                    cc=cc,
                    bcc=bcc,
                    subject=subject,
                    body=body,
                    reply_to_message_id=reply_to_message_id,
                ),
                "saveToSentItems": True,
            },
            timeout=30,
        )
        self._raise_for_status(response)
        return EmailExecutionResult(
            action="send",
            message_id=None,
            thread_id=thread_id,
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
        sender = self._get_sender_email()
        response = requests.post(
            f"{self.GRAPH_BASE_URL}/users/{sender}/messages",
            headers=self._build_headers(),
            json=self._build_message(
                to=to,
                cc=cc,
                bcc=bcc,
                subject=subject,
                body=body,
                reply_to_message_id=reply_to_message_id,
            ),
            timeout=30,
        )
        self._raise_for_status(response)
        payload = response.json()
        return EmailExecutionResult(
            action="draft",
            message_id=payload.get("id"),
            draft_id=payload.get("id"),
            thread_id=payload.get("conversationId") or thread_id,
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
