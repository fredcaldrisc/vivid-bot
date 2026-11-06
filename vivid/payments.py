"""Subscriptions via Paystack (cards and Ghana mobile money)."""

import hashlib
import hmac
import logging
import uuid

import requests

from . import PRODUCT_NAME

log = logging.getLogger(__name__)


class Paystack:
    API = "https://api.paystack.co"

    def __init__(self, secret_key: str, amount_pesewas: int, callback_url: str = ""):
        self.secret_key = secret_key
        self.amount = amount_pesewas
        self.callback_url = callback_url

    @property
    def enabled(self) -> bool:
        return bool(self.secret_key)

    def create_checkout(self, phone: str) -> tuple[str, str]:
        """Returns (reference, payment_url) for one subscription period."""
        reference = f"vivid-{phone}-{uuid.uuid4().hex[:10]}"
        payload = {
            # Paystack requires an email; WhatsApp gives us a phone number only.
            "email": f"{phone}@subscribers.vivid.invalid",
            "amount": self.amount,
            "currency": "GHS",
            "reference": reference,
            "metadata": {"phone": phone, "product": PRODUCT_NAME},
        }
        if self.callback_url:
            payload["callback_url"] = self.callback_url
        resp = requests.post(
            f"{self.API}/transaction/initialize",
            json=payload,
            headers={"Authorization": f"Bearer {self.secret_key}"},
            timeout=20,
        )
        resp.raise_for_status()
        return reference, resp.json()["data"]["authorization_url"]

    def valid_signature(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self.secret_key.encode(), raw_body, hashlib.sha512).hexdigest()
        return bool(self.secret_key) and hmac.compare_digest(expected, signature or "")
