"""SMS fallback through Arkesel (Ghana: Telecel, MTN, AT).

Used when a WhatsApp reminder can't reach the subscriber's phone (no data,
phone off, or WhatsApp send failed).

Arkesel SMS API v2: POST https://sms.arkesel.com/api/v2/sms/send
  header  api-key: <your key>
  json    {"sender": "VIVID", "message": "...", "recipients": ["233241234567"]}
The sender ID (max 11 characters) must be approved in your Arkesel dashboard first.
"""

import logging

import requests

log = logging.getLogger(__name__)


class ArkeselSMS:
    URL = "https://sms.arkesel.com/api/v2/sms/send"

    def __init__(self, api_key: str, sender: str = "VIVID", timeout: float = 20.0):
        self.api_key = api_key
        self.sender = sender[:11]
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def send(self, phone: str, message: str) -> bool:
        if not self.enabled:
            log.warning("SMS fallback skipped: ARKESEL_API_KEY is not set")
            return False
        try:
            resp = requests.post(
                self.URL,
                json={"sender": self.sender, "message": message[:459], "recipients": [phone]},
                headers={"api-key": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException:
            log.exception("Arkesel request failed")
            return False
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or str(body.get("status", "")).lower() not in {"success", "ok"}:
            log.warning("Arkesel SMS failed (%s): %s", resp.status_code, resp.text[:300])
            return False
        return True
