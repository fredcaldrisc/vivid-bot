"""Thin client for the WhatsApp Cloud API (Meta Graph API)."""

import logging

import requests

log = logging.getLogger(__name__)


class WhatsAppError(RuntimeError):
    pass


class WhatsApp:
    def __init__(self, token: str, phone_number_id: str, graph_version: str = "v23.0", timeout: float = 20.0):
        self.token = token
        self.phone_number_id = phone_number_id
        self.base = f"https://graph.facebook.com/{graph_version}"
        self.timeout = timeout

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _send(self, payload: dict) -> str | None:
        """Sends a message and returns its WhatsApp message id (wamid)."""
        body = {"messaging_product": "whatsapp", **payload}
        resp = requests.post(
            f"{self.base}/{self.phone_number_id}/messages", json=body, headers=self._auth, timeout=self.timeout
        )
        if resp.status_code >= 400:
            raise WhatsAppError(f"WhatsApp send failed ({resp.status_code}): {resp.text}")
        messages = resp.json().get("messages") or [{}]
        return messages[0].get("id")

    def send_text(self, to: str, text: str) -> str | None:
        return self._send({"to": to, "type": "text", "text": {"body": text[:4096]}})

    def send_audio(self, to: str, media_id: str) -> str | None:
        return self._send({"to": to, "type": "audio", "audio": {"id": media_id}})

    def send_buttons(self, to: str, text: str, buttons: list[tuple[str, str]]) -> str | None:
        """Up to 3 reply buttons as (id, title); titles max 20 characters."""
        return self._send(
            {
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text[:1024]},
                    "action": {
                        "buttons": [{"type": "reply", "reply": {"id": bid, "title": title[:20]}} for bid, title in buttons[:3]]
                    },
                },
            }
        )

    def send_template(
        self, to: str, name: str, lang: str, body_params: list[str], button_payload: str | None = None
    ) -> str | None:
        # Template parameters may not contain newlines/tabs or 4+ consecutive spaces.
        params = [{"type": "text", "text": " ".join(p.split())[:1000]} for p in body_params]
        components = [{"type": "body", "parameters": params}]
        if button_payload:
            components.append(
                {"type": "button", "sub_type": "quick_reply", "index": "0",
                 "parameters": [{"type": "payload", "payload": button_payload}]}
            )
        return self._send(
            {
                "to": to,
                "type": "template",
                "template": {"name": name, "language": {"code": lang}, "components": components},
            }
        )

    def ensure_subscribed(self, waba_ids: list[str] | None = None) -> list[str]:
        """Makes sure each WhatsApp Business Account sends its webhooks to this app.

        Without this link Meta receives users' messages but never forwards them, even when the
        app's own webhook is configured. WABA ids come from the token's scopes when not given.
        Returns human-readable lines describing what happened (safe to log).
        """
        report = []
        debug = requests.get(
            f"{self.base}/debug_token",
            params={"input_token": self.token, "access_token": self.token},
            timeout=self.timeout,
        )
        if debug.status_code >= 400:
            return [f"Could not inspect the WhatsApp token ({debug.status_code}): {debug.text[:300]}"]
        data = debug.json().get("data", {})
        app_id = str(data.get("app_id", ""))
        if not waba_ids:
            waba_ids = sorted({
                str(t) for scope in data.get("granular_scopes", [])
                if scope.get("scope", "").startswith("whatsapp_business") for t in scope.get("target_ids", [])
            })
        if not waba_ids:
            return ["The WhatsApp token has no WhatsApp Business Account assigned. Assign the account to "
                    "the system user and generate a new token."]
        for waba in waba_ids:
            url = f"{self.base}/{waba}/subscribed_apps"
            current = requests.get(url, headers=self._auth, timeout=self.timeout)
            if current.status_code >= 400:
                report.append(f"WABA {waba}: could not read subscriptions ({current.status_code}): {current.text[:300]}")
                continue
            subscribed = {
                str((entry.get("whatsapp_business_api_data") or {}).get("id", entry.get("id", "")))
                for entry in current.json().get("data", [])
            }
            if app_id and app_id in subscribed:
                report.append(f"WABA {waba}: already sends webhooks to app {app_id}")
                continue
            added = requests.post(url, headers=self._auth, timeout=self.timeout)
            if added.status_code >= 400:
                report.append(f"WABA {waba}: subscribing app {app_id} FAILED ({added.status_code}): {added.text[:300]}")
            else:
                report.append(f"WABA {waba}: subscribed app {app_id}, so incoming messages will now be forwarded")
        return report

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        meta = requests.get(f"{self.base}/{media_id}", headers=self._auth, timeout=self.timeout)
        if meta.status_code >= 400:
            raise WhatsAppError(f"Media lookup failed ({meta.status_code}): {meta.text}")
        info = meta.json()
        data = requests.get(info["url"], headers=self._auth, timeout=self.timeout)
        if data.status_code >= 400:
            raise WhatsAppError(f"Media download failed ({data.status_code})")
        return data.content, info.get("mime_type", "audio/ogg")

    def upload_media(self, content: bytes, mime: str, filename: str = "voice.ogg") -> str:
        resp = requests.post(
            f"{self.base}/{self.phone_number_id}/media",
            headers=self._auth,
            data={"messaging_product": "whatsapp", "type": mime},
            files={"file": (filename, content, mime)},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise WhatsAppError(f"Media upload failed ({resp.status_code}): {resp.text}")
        return resp.json()["id"]
