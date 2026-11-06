"""All settings come from environment variables (or a local .env file)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


def _secret(name: str) -> str:
    """Reads a token, forgiving common paste mistakes: spaces, line breaks, quotes, 'Bearer ',
    and invisible characters (zero-width spaces, byte-order marks) that copying from web pages adds."""
    raw = os.environ.get(name, "")
    value = "".join(c for c in raw if c.isascii() and c.isprintable() and not c.isspace()).strip("\"'")
    if value.lower().startswith("bearer"):
        value = value[len("bearer"):]
    return value


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Meta / WhatsApp Cloud API
    verify_token: str = field(default_factory=lambda: os.environ.get("VERIFY_TOKEN", ""))
    app_secret: str = field(default_factory=lambda: os.environ.get("APP_SECRET", ""))
    whatsapp_token: str = field(default_factory=lambda: _secret("WHATSAPP_TOKEN"))
    # PHONE_NUMBER_ID is the name the first version of the bot used on Render.
    phone_number_id: str = field(
        default_factory=lambda: os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or os.environ.get("PHONE_NUMBER_ID", "")
    )
    graph_version: str = field(default_factory=lambda: os.environ.get("GRAPH_API_VERSION", "v23.0"))
    require_signature: bool = field(default_factory=lambda: _bool("REQUIRE_SIGNATURE", "true"))
    # Approved template used when a reminder fires more than 24h after the user's last message.
    reminder_template: str = field(default_factory=lambda: os.environ.get("REMINDER_TEMPLATE", "vivid_reminder"))
    reminder_template_lang: str = field(default_factory=lambda: os.environ.get("REMINDER_TEMPLATE_LANG", "en"))

    # Claude
    anthropic_model: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"))

    # Speech-to-text for voice notes (GhanaNLP Khaya handles Twi and English)
    asr_url: str = field(default_factory=lambda: os.environ.get("ASR_URL", ""))
    asr_key: str = field(default_factory=lambda: os.environ.get("ASR_KEY", ""))

    # Subscriptions (Paystack, supports Ghana mobile money)
    paystack_secret: str = field(default_factory=lambda: os.environ.get("PAYSTACK_SECRET_KEY", ""))
    price_pesewas: int = field(default_factory=lambda: int(os.environ.get("SUBSCRIPTION_PRICE_PESEWAS", "2000")))
    subscription_days: int = field(default_factory=lambda: int(os.environ.get("SUBSCRIPTION_DAYS", "30")))
    public_base_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_BASE_URL", ""))

    # SMS fallback (Arkesel)
    arkesel_api_key: str = field(default_factory=lambda: os.environ.get("ARKESEL_API_KEY", ""))
    sms_sender: str = field(default_factory=lambda: os.environ.get("SMS_SENDER_ID", "VIVID"))
    # Send an SMS if WhatsApp hasn't reached the phone this many minutes after the reminder fired.
    sms_fallback_minutes: int = field(default_factory=lambda: int(os.environ.get("SMS_FALLBACK_MINUTES", "5")))
    # A fired reminder not marked Done within this many minutes becomes Missed.
    missed_after_minutes: int = field(default_factory=lambda: int(os.environ.get("MISSED_AFTER_MINUTES", "120")))

    # App
    admin_token: str = field(default_factory=lambda: os.environ.get("ADMIN_TOKEN", ""))
    timezone: str = field(default_factory=lambda: os.environ.get("VIVID_TIMEZONE", "Africa/Accra"))
    database_path: str = field(default_factory=lambda: os.environ.get("DATABASE_PATH", str(PROJECT_DIR / "data" / "vivid.db")))
    audio_dir: str = field(default_factory=lambda: os.environ.get("AUDIO_DIR", str(PROJECT_DIR / "data" / "audio")))
    run_scheduler: bool = field(default_factory=lambda: _bool("RUN_SCHEDULER", "true"))
    scheduler_interval: int = field(default_factory=lambda: int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "20")))
