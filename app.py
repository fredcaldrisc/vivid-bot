"""VIVID web service: WhatsApp webhook, Paystack webhook, admin API, scheduler.

Run with ONE worker process (the scheduler lives inside it):
    gunicorn -w 1 --threads 8 app:app
"""

import hmac
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, request

from vivid import BOT_NAME
from vivid.ai import ReminderAI
from vivid.bot import VividBot
from vivid.config import Settings
from vivid.db import Database
from vivid.payments import Paystack
from vivid.scheduler import start_scheduler
from vivid.sms import ArkeselSMS
from vivid.speech import Transcriber
from vivid.whatsapp import WhatsApp

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vivid")


FALLBACK_DATA_DIR = Path(__file__).resolve().parent / "data"


def usable_dir(directory: Path, purpose: str) -> Path:
    """Returns `directory` if it can be written to; otherwise the project's own data/ folder.

    On Render, /var/data only exists once a persistent disk is mounted there. Without the
    disk VIVID still starts, but everything it stores is lost on the next deploy or restart.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return directory
    except OSError as exc:
        log.error(
            "Cannot write %s to %s (%s). Using %s instead. THIS STORAGE IS TEMPORARY: "
            "reminders and voice notes will be lost on the next deploy. Add a persistent disk "
            "mounted at %s.", purpose, directory, exc, FALLBACK_DATA_DIR, directory,
        )
        FALLBACK_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return FALLBACK_DATA_DIR


def build_bot(settings: Settings) -> VividBot:
    callback = f"{settings.public_base_url.rstrip('/')}/paid" if settings.public_base_url else ""
    db_path = Path(settings.database_path)
    db_path = usable_dir(db_path.parent, "the database") / db_path.name
    audio_dir = usable_dir(Path(settings.audio_dir), "voice notes")
    if audio_dir == FALLBACK_DATA_DIR:
        audio_dir = FALLBACK_DATA_DIR / "audio"
    return VividBot(
        db=Database(str(db_path)),
        whatsapp=WhatsApp(settings.whatsapp_token, settings.phone_number_id, settings.graph_version),
        ai=ReminderAI(settings.anthropic_model),
        transcriber=Transcriber(settings.asr_url, settings.asr_key),
        payments=Paystack(settings.paystack_secret, settings.price_pesewas, callback),
        sms=ArkeselSMS(settings.arkesel_api_key, settings.sms_sender),
        sms_fallback_minutes=settings.sms_fallback_minutes,
        missed_after_minutes=settings.missed_after_minutes,
        tz=settings.timezone,
        audio_dir=str(audio_dir),
        template_name=settings.reminder_template,
        template_lang=settings.reminder_template_lang,
        subscription_days=settings.subscription_days,
    )


def create_app(settings: Settings | None = None, bot: VividBot | None = None, run_async: bool = True) -> Flask:
    settings = settings or Settings()
    bot = bot or build_bot(settings)
    executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="vivid-msg") if run_async else None

    app = Flask("vivid")
    app.config["SETTINGS"] = settings
    app.config["BOT"] = bot

    def valid_meta_signature(payload: bytes) -> bool:
        header = request.headers.get("X-Hub-Signature-256", "")
        if not settings.app_secret or not header.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(settings.app_secret.encode(), payload, "sha256").hexdigest()
        return hmac.compare_digest(expected, header)

    def is_admin() -> bool:
        token = request.headers.get("X-Admin-Token", "")
        return bool(settings.admin_token) and hmac.compare_digest(settings.admin_token, token)

    @app.get("/")
    def home():
        return f"<h1>{BOT_NAME} is live</h1>"

    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    # /webhook/whatsapp is kept because the first version of the bot answered there too.
    @app.get("/webhook")
    @app.get("/webhook/whatsapp")
    def verify():
        if not settings.verify_token:
            return jsonify(error="VERIFY_TOKEN is not configured"), 503
        if hmac.compare_digest(settings.verify_token, request.args.get("hub.verify_token", "")):
            return request.args.get("hub.challenge", ""), 200
        return jsonify(error="verification failed"), 403

    @app.post("/webhook")
    @app.post("/webhook/whatsapp")
    def incoming():
        raw = request.get_data(cache=True)
        if settings.require_signature and not valid_meta_signature(raw):
            log.error("Rejected webhook: bad or missing X-Hub-Signature-256. Is APP_SECRET set to the Meta app secret?")
            return jsonify(error="invalid webhook signature"), 401
        data = request.get_json(silent=True)
        if data is None:
            return jsonify(error="expected a JSON body"), 400
        # Answer Meta immediately; Claude/ASR calls can take a few seconds.
        if executor:
            executor.submit(bot.handle_webhook, data)
        else:
            bot.handle_webhook(data)
        return jsonify(status="ok"), 200

    @app.post("/paystack/webhook")
    def paystack_webhook():
        raw = request.get_data(cache=True)
        if not bot.payments.valid_signature(raw, request.headers.get("x-paystack-signature", "")):
            return jsonify(error="invalid signature"), 401
        event = request.get_json(silent=True) or {}
        if event.get("event") == "charge.success":
            reference = (event.get("data") or {}).get("reference", "")
            if bot.confirm_payment(reference):
                log.info("Subscription activated for payment %s", reference)
        return jsonify(status="ok"), 200

    @app.get("/paid")
    def paid():
        return f"<h1>Thank you!</h1><p>Go back to WhatsApp. {BOT_NAME} will confirm your subscription there.</p>"

    @app.post("/admin/subscribers")
    def grant_subscription():
        """Manually activate a subscriber: {"phone": "233241234567", "days": 30}"""
        if not is_admin():
            return jsonify(error="unauthorised"), 401
        body = request.get_json(silent=True) or {}
        phone = "".join(ch for ch in str(body.get("phone", "")) if ch.isdigit())
        if not phone:
            return jsonify(error="phone is required (international format, digits only)"), 400
        until = bot.extend_subscription(phone, int(body.get("days") or settings.subscription_days))
        return jsonify(phone=phone, subscribed_until=until.isoformat()), 200

    missing = [name for name, value in [
        ("VERIFY_TOKEN", settings.verify_token), ("WHATSAPP_TOKEN", settings.whatsapp_token),
        ("WHATSAPP_PHONE_NUMBER_ID", settings.phone_number_id),
        ("APP_SECRET", settings.app_secret if settings.require_signature else "ok"),
    ] if not value]
    if settings.whatsapp_token:
        # Never log the token itself; length and the first 3 characters are enough to spot a wrong paste.
        raw = os.environ.get("WHATSAPP_TOKEN", "")
        if settings.whatsapp_token.startswith("EAA"):
            log.info("WhatsApp token loaded: %d characters, looks like a Meta token (starts with EAA). "
                     "%d hidden/extra characters were removed.", len(settings.whatsapp_token),
                     len(raw) - len(settings.whatsapp_token))
        else:
            log.error("WhatsApp token loaded: %d characters but does NOT start with EAA; it starts with %s. "
                      "This is probably not a Meta access token.", len(settings.whatsapp_token),
                      ascii(settings.whatsapp_token[:3]))
    if missing:
        log.error("Missing settings: %s. VIVID cannot receive or send WhatsApp messages until they are set.", ", ".join(missing))

    if settings.run_scheduler:
        start_scheduler(bot, settings.scheduler_interval)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
else:
    # Imported by gunicorn ("app:app"). Tests import create_app directly with their own settings.
    if os.environ.get("VIVID_SKIP_APP") != "1":
        app = create_app()
