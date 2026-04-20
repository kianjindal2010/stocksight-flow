from __future__ import annotations

import requests

from ..config import Settings


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.resend_api_key and self.settings.resend_from)

    def send(self, to_email: str, subject: str, body: str) -> None:
        if not self.enabled():
            return
        response = requests.post(
            f"{self.settings.resend_base_url}/emails",
            headers={
                "Authorization": f"Bearer {self.settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": self.settings.resend_from,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=self.settings.resend_timeout_seconds,
        )
        if response.status_code >= 400:
            try:
                details = response.json()
            except ValueError:
                details = response.text
            raise RuntimeError(f"Resend email send failed: {details}")
