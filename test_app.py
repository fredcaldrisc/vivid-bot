import hashlib
import hmac
import json
import os
from datetime import timedelta

os.environ["VIVID_SKIP_APP"] = "1"

import pytest

from app import create_app
from vivid.ai import Understanding
from vivid.bot import VividBot
from vivid.config import Settings
from vivid.db import Database, iso, utcnow
from vivid.payments import Paystack

PHONE = "233241234567"


class FakeWhatsApp:
    def __init__(self):
        self.sent = []
        self.fail = False

    def _record(self, *item):
        if self.fail:
            raise RuntimeError("WhatsApp down")
        self.sent.append(item)
        return f"wamid.out.{len(self.sent)}"

    def send_text(self, to, text):
        return self._record("text", to, text)

    def send_audio(self, to, media_id):
        return self._record("audio", to, media_id)

    def send_buttons(self, to, text, buttons):
        return self._record("buttons", to, text, buttons)

    def send_template(self, to, name, lang, params, button_payload=None):
        return self._record("template", to, params[0], button_payload)

    def download_media(self, media_id):
        return b"OggS-fake-voice", "audio/ogg; codecs=opus"

    def upload_media(self, content, mime, filename="voice.ogg"):
        assert content == b"OggS-fake-voice"
        return "uploaded-media-1"

    def last_text(self):
        return [m for m in self.sent if m[0] in ("text", "buttons")][-1][2]


class FakeSMS:
    enabled = True

    def __init__(self):
        self.sent = []

    def send(self, phone, message):
        self.sent.append((phone, message))
        return True


class FakeAI:
    """Pretends to be Claude: due time is always 2 hours from now."""

    def understand(self, text, now_local):
        due = (now_local + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        if "kwame" in text.lower():
            return Understanding(is_reminder=True, task="call driver Kwame", who="driver Kwame", due_local=due, language="en")
        if "remind" in text.lower():
            return Understanding(is_reminder=True, task="call mom", who="mom", due_local=due, language="en")
        if "pm" in text.lower():
            return Understanding(is_reminder=True, task="", who="", due_local=due, language="en")
        return Understanding(is_reminder=False, task="", who="", due_local="", language="en")

    def rewrite(self, vivid, task):
        if "Kwame" in vivid:
            return "Time to call driver Kwame to ask him to go and service the truck after his trip."
        return "Time to call mom to ask her if she has taken her medication."


class FakeASR:
    enabled = False

    def transcribe(self, *a, **k):
        return None


@pytest.fixture
def env(tmp_path):
    wa = FakeWhatsApp()
    sms = FakeSMS()
    bot = VividBot(
        db=Database(str(tmp_path / "t.db")),
        whatsapp=wa,
        ai=FakeAI(),
        transcriber=FakeASR(),
        payments=Paystack("sk_test_secret", 2000),
        sms=sms,
        audio_dir=str(tmp_path / "audio"),
    )
    wa.sms = sms
    settings = Settings(
        verify_token="verify-me", app_secret="app-secret", admin_token="admin-token",
        run_scheduler=False, database_path=str(tmp_path / "unused.db"),
    )
    app = create_app(settings, bot=bot, run_async=False)
    return app.test_client(), bot, wa


_ids = iter(range(10_000))


def text_msg(body):
    return {"from": PHONE, "id": f"wamid.{next(_ids)}", "type": "text", "text": {"body": body}}


def voice_msg():
    return {"from": PHONE, "id": f"wamid.{next(_ids)}", "type": "audio", "audio": {"id": "media-9", "mime_type": "audio/ogg", "voice": True}}


def webhook(client, msg):
    body = json.dumps({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": PHONE, "profile": {"name": "Ama Mensah"}}], "messages": [msg]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    return client.post("/webhook", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sig})


def make_due(bot):
    bot.db._exec("UPDATE reminders SET due_at = ?", (iso(utcnow() - timedelta(seconds=1)),))


def age_fired(bot, minutes):
    bot.db._exec("UPDATE reminders SET fired_at = ?", (iso(utcnow() - timedelta(minutes=minutes)),))


def status_update(client, wamid, status):
    body = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": wamid, "status": status, "recipient_id": PHONE}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    return client.post("/webhook", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sig})


def create_reminder(client, casual="Remind me to call mom at 6:30pm", vivid="to ask her if she has taken her medication"):
    webhook(client, text_msg(casual))
    webhook(client, text_msg(vivid))


def test_health_and_meta_verification(env):
    client, _, _ = env
    assert client.get("/health").get_json() == {"status": "ok"}
    assert client.get("/webhook?hub.verify_token=verify-me&hub.challenge=abc").get_data(as_text=True) == "abc"
    assert client.get("/webhook?hub.verify_token=wrong").status_code == 403
    assert client.post("/webhook", data=b"{}", content_type="application/json").status_code == 401


def test_unsubscribed_user_is_asked_to_subscribe(env, monkeypatch):
    client, bot, wa = env
    monkeypatch.setattr(bot.payments, "create_checkout", lambda phone: ("ref-1", "https://pay.example/ref-1"))
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    assert "Vivid Reminders" in wa.last_text() and "https://pay.example/ref-1" in wa.last_text()
    assert bot.db.pending_reminders(PHONE) == []


def test_paystack_webhook_activates_subscription(env, monkeypatch):
    client, bot, wa = env
    monkeypatch.setattr(bot.payments, "create_checkout", lambda phone: ("ref-1", "https://pay.example/ref-1"))
    webhook(client, text_msg("hi"))
    body = json.dumps({"event": "charge.success", "data": {"reference": "ref-1"}}).encode()
    assert client.post("/paystack/webhook", data=body, content_type="application/json", headers={"x-paystack-signature": "bad"}).status_code == 401
    sig = hmac.new(b"sk_test_secret", body, hashlib.sha512).hexdigest()
    assert client.post("/paystack/webhook", data=body, content_type="application/json", headers={"x-paystack-signature": sig}).status_code == 200
    assert bot.is_subscribed(bot.db.get_user(PHONE))
    assert "Payment received" in wa.last_text()


def test_typed_reminder_is_rewritten_and_delivered(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    assert "vivid description" in wa.last_text()
    webhook(client, text_msg("remind me to call mom at 6:30pm to ask her if she has taken her medication"))
    assert "Saved" in wa.last_text()
    [reminder] = bot.db.pending_reminders(PHONE)
    assert reminder["vivid_kind"] == "text"

    assert bot.fire_due() == 0  # not due yet
    make_due(bot)
    assert bot.fire_due() == 1
    assert wa.last_text().endswith("Time to call mom to ask her if she has taken her medication.")
    assert bot.fire_due() == 0  # never twice


def test_voice_vivid_description_is_played_back(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    webhook(client, voice_msg())
    [reminder] = bot.db.pending_reminders(PHONE)
    assert reminder["vivid_kind"] == "voice" and os.path.exists(reminder["audio_path"])
    make_due(bot)
    bot.fire_due()
    assert wa.sent[-2] == ("audio", PHONE, "uploaded-media-1")
    assert wa.sent[-1][0] == "buttons"  # Done button follows the voice note


def test_voice_casual_without_asr_asks_for_time(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, voice_msg())
    assert "What time" in wa.last_text()
    webhook(client, text_msg("6:30pm"))
    assert "vivid description" in wa.last_text()


def test_outside_24h_window_uses_template_then_plays_voice_on_reply(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    webhook(client, voice_msg())
    bot.db._exec("UPDATE users SET last_inbound_at = ?", (iso(utcnow() - timedelta(days=2)),))
    make_due(bot)
    bot.fire_due()
    assert wa.sent[-1][0] == "template"
    [reminder_id] = [r[0] for r in bot.db._exec("SELECT id FROM reminders").fetchall()]
    assert wa.sent[-1][3] == f"open:{reminder_id}"
    webhook(client, {"from": PHONE, "id": "wamid.btn", "type": "button", "button": {"payload": f"open:{reminder_id}", "text": "Open"}})
    assert ("audio", PHONE, "uploaded-media-1") in wa.sent[-3:]


def test_who_is_captured_and_reported_form_sent(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("Remind me to call driver Kwame on Friday 1pm"))
    assert "Who: driver Kwame" in wa.last_text()
    webhook(client, text_msg("Remind me to call driver Kwame to tell him to go and service the truck on Friday 1pm after his trip"))
    [reminder] = bot.db.pending_reminders(PHONE)
    assert reminder["who"] == "driver Kwame"
    make_due(bot)
    bot.tick()
    assert wa.sent[-1][0] == "buttons"
    assert "Time to call driver Kwame to ask him to go and service the truck after his trip." in wa.sent[-1][2]


def test_sms_sent_when_whatsapp_not_delivered_in_time(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    bot.tick()
    assert wa.sms.sent == []          # give WhatsApp a few minutes first
    age_fired(bot, 6)
    bot.tick()
    assert len(wa.sms.sent) == 1 and wa.sms.sent[0][0] == PHONE
    assert "Time to call mom" in wa.sms.sent[0][1]
    bot.tick()
    assert len(wa.sms.sent) == 1      # only once


def test_no_sms_when_whatsapp_delivered(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    bot.tick()
    wamid = f"wamid.out.{len(wa.sent)}"
    status_update(client, wamid, "delivered")
    age_fired(bot, 30)
    bot.tick()
    assert wa.sms.sent == []
    assert bot.db._exec("SELECT delivery FROM reminders").fetchone()[0] == "delivered"


def test_sms_immediately_when_whatsapp_send_fails(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    wa.fail = True
    bot.tick()
    assert len(wa.sms.sent) == 1


def test_sms_when_whatsapp_reports_failed_status(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    bot.tick()
    status_update(client, f"wamid.out.{len(wa.sent)}", "failed")
    assert len(wa.sms.sent) == 1


def test_done_button_missed_and_list_sections(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)                                   # #1 -> Done
    create_reminder(client)                                   # #2 -> Missed
    make_due(bot)
    bot.tick()
    create_reminder(client)                                   # #3 -> Upcoming
    webhook(client, {"from": PHONE, "id": "wamid.done1", "type": "interactive",
                     "interactive": {"type": "button_reply", "button_reply": {"id": "done:1", "title": "✅ Done"}}})
    assert "marked as *Done*" in wa.last_text()
    bot.db._exec("UPDATE reminders SET fired_at = ? WHERE id = 2", (iso(utcnow() - timedelta(hours=3)),))
    bot.tick()
    webhook(client, text_msg("list"))
    listing = wa.last_text()
    upcoming, done, missed = listing.index("Upcoming"), listing.index("*Done*"), listing.index("Missed")
    assert upcoming < listing.index("#3") < done < listing.index("#1") < missed < listing.index("#2")


def test_typing_done_marks_latest_due_reminder(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    bot.tick()
    webhook(client, text_msg("Done"))
    assert bot.db.get_reminder(1)["outcome"] == "done"


def test_list_and_cancel(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    webhook(client, text_msg("to ask about her medication"))
    [reminder] = bot.db.pending_reminders(PHONE)
    webhook(client, text_msg("list"))
    assert f"#{reminder['id']}" in wa.last_text()
    webhook(client, text_msg(f"cancel {reminder['id']}"))
    assert bot.db.pending_reminders(PHONE) == []


def test_duplicate_webhook_delivery_is_ignored(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    msg = text_msg("Remind me to call mom at 6:30pm")
    webhook(client, msg)
    webhook(client, msg)
    assert len(wa.sent) == 1


def test_admin_can_grant_subscription(env):
    client, bot, _ = env
    assert client.post("/admin/subscribers", json={"phone": PHONE}).status_code == 401
    r = client.post("/admin/subscribers", json={"phone": "+233 24 123 4567", "days": 7}, headers={"X-Admin-Token": "admin-token"})
    assert r.status_code == 200 and r.get_json()["phone"] == PHONE
    assert bot.is_subscribed(bot.db.get_user(PHONE))


def test_missing_disk_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    import app as app_module

    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the disk folder should be")
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(app_module, "FALLBACK_DATA_DIR", fallback)
    settings = Settings(
        database_path=str(blocker / "vivid.db"), audio_dir=str(blocker / "audio"), run_scheduler=False,
    )
    bot = app_module.build_bot(settings)
    assert bot.audio_dir == fallback / "audio"
    assert (fallback / "vivid.db").exists()
