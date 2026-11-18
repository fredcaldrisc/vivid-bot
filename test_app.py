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
        payments=Paystack("sk_test_secret"),
        sms=sms,
        audio_dir=str(tmp_path / "audio"),
    )
    wa.sms = sms
    settings = Settings(
        verify_token="verify-me", app_secret="app-secret", admin_token="admin-token",
        run_scheduler=False, database_path=str(tmp_path / "unused.db"), premium_enabled=True,
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
    monkeypatch.setattr(bot.payments, "create_checkout", lambda phone, plan: (f"ref-{plan.key}", f"https://pay.example/{plan.key}"))
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    menu = wa.last_text()
    assert "Standard*: GHS 30 for 20 days" in menu and "Premium*: GHS 70 for 30 days" in menu and "Reply *1* or *2*" in menu
    assert bot.db.pending_reminders(PHONE) == []
    webhook(client, text_msg("2"))
    assert "https://pay.example/premium" in wa.last_text() and "GHS 70" in wa.last_text()


def test_paystack_webhook_activates_subscription(env, monkeypatch):
    client, bot, wa = env
    monkeypatch.setattr(bot.payments, "create_checkout", lambda phone, plan: ("ref-1", "https://pay.example/ref-1"))
    webhook(client, text_msg("hi"))
    webhook(client, text_msg("premium"))
    body = json.dumps({"event": "charge.success", "data": {"reference": "ref-1"}}).encode()
    assert client.post("/paystack/webhook", data=body, content_type="application/json", headers={"x-paystack-signature": "bad"}).status_code == 401
    sig = hmac.new(b"sk_test_secret", body, hashlib.sha512).hexdigest()
    assert client.post("/paystack/webhook", data=body, content_type="application/json", headers={"x-paystack-signature": sig}).status_code == 200
    assert bot.is_subscribed(bot.db.get_user(PHONE))
    assert bot.plan_of(bot.db.get_user(PHONE)) == "premium"
    assert "Payment received" in wa.last_text() and "Premium" in wa.last_text()


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
    assert "Time to call mom to ask her if she has taken her medication." in wa.last_text()
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
    bot.extend_subscription(PHONE, plan="premium")
    create_reminder(client)
    make_due(bot)
    bot.tick()
    assert wa.sms.sent == []          # give WhatsApp a few minutes first
    age_fired(bot, 6)
    bot.tick()
    assert len(wa.sms.sent) == 1 and wa.sms.sent[0][0] == PHONE
    assert "Time to call mom" in wa.sms.sent[0][1]
    bot.tick()
    assert len(wa.sms.sent) == 1      # next one waits for the schedule (15 min)
    age_fired(bot, 16)
    bot.tick()
    assert len(wa.sms.sent) == 2 and "[reminder 2 of 3]" in wa.sms.sent[1][1]
    age_fired(bot, 31)
    bot.tick()
    age_fired(bot, 90)
    bot.tick()
    assert len(wa.sms.sent) == 3      # Premium: at most 3 SMS per reminder


def test_no_sms_when_whatsapp_delivered(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE, plan="premium")
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
    bot.extend_subscription(PHONE, plan="premium")
    create_reminder(client)
    make_due(bot)
    wa.fail = True
    bot.tick()
    assert len(wa.sms.sent) == 1


def test_sms_when_whatsapp_reports_failed_status(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE, plan="premium")
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


def test_public_pages_for_meta(env):
    client, _, _ = env
    for path, words in [("/privacy", "What we collect"), ("/terms", "Terms of service"), ("/data-deletion", "DELETE ALL")]:
        response = client.get(path)
        assert response.status_code == 200 and words in response.get_data(as_text=True)


def test_delete_my_data_needs_confirmation_and_removes_everything(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("Remind me to call mom at 6:30pm"))
    webhook(client, voice_msg())
    [reminder] = bot.db.pending_reminders(PHONE)
    audio = reminder["audio_path"]

    webhook(client, text_msg("delete my data"))
    assert "DELETE ALL" in wa.last_text()
    webhook(client, text_msg("no thanks"))
    assert "nothing was deleted" in wa.last_text()
    assert bot.db.pending_reminders(PHONE)

    webhook(client, text_msg("Delete my data"))
    webhook(client, text_msg("DELETE ALL"))
    assert "deleted" in wa.last_text()
    assert bot.db.pending_reminders(PHONE) == []
    assert bot.db.get_user(PHONE) is None
    assert not os.path.exists(audio)


def test_ensure_subscribed_links_waba_to_app(monkeypatch):
    from vivid import whatsapp as wa_module

    class Resp:
        def __init__(self, status, body):
            self.status_code, self._body, self.text = status, body, str(body)

        def json(self):
            return self._body

    calls = []
    state = {"subscribed": False}

    def fake_get(url, **kwargs):
        if url.endswith("/debug_token"):
            return Resp(200, {"data": {"app_id": "777", "granular_scopes": [
                {"scope": "whatsapp_business_messaging", "target_ids": ["555"]}]}})
        data = [{"whatsapp_business_api_data": {"id": "777"}}] if state["subscribed"] else []
        return Resp(200, {"data": data})

    def fake_post(url, **kwargs):
        calls.append(url)
        state["subscribed"] = True
        return Resp(200, {"success": True})

    monkeypatch.setattr(wa_module.requests, "get", fake_get)
    monkeypatch.setattr(wa_module.requests, "post", fake_post)
    client = wa_module.WhatsApp("token", "123")
    first = client.ensure_subscribed()
    assert calls and calls[0].endswith("/555/subscribed_apps") and "subscribed app 777" in first[0]
    second = client.ensure_subscribed()
    assert len(calls) == 1 and "already" in second[0]


def test_owner_numbers_have_access_without_subscription(tmp_path):
    wa = FakeWhatsApp()
    bot = VividBot(
        db=Database(str(tmp_path / "owner.db")), whatsapp=wa, ai=FakeAI(), transcriber=FakeASR(),
        payments=Paystack("sk_test_secret"), audio_dir=str(tmp_path / "audio"),
        owner_numbers={PHONE},
    )
    bot.handle_message(text_msg("status"))
    assert "owner access" in wa.last_text() and "Premium" in wa.last_text()
    bot.handle_message(text_msg("Remind me to call mom at 6:30pm"))
    assert "vivid description" in wa.last_text()
    bot.handle_message({"from": "233200000000", "id": "wamid.stranger", "type": "text", "text": {"body": "hi"}})
    assert "Choose a Vivid Reminders plan" in wa.last_text()


def test_owner_numbers_setting_is_parsed(monkeypatch):
    monkeypatch.setenv("OWNER_NUMBERS", "+233 54 753 9948, 233201234567")
    assert Settings().owner_numbers == {"233547539948", "233201234567"}


def test_website_pages_show_price_from_settings_and_whatsapp_link(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PUBLIC_NUMBER", "+233 20 123 4567")
    bot = VividBot(
        db=Database(str(tmp_path / "t.db")), whatsapp=FakeWhatsApp(), ai=FakeAI(), transcriber=FakeASR(),
        payments=Paystack("sk_test_secret"), sms=FakeSMS(), audio_dir=str(tmp_path / "audio"),
    )
    settings = Settings(verify_token="v", app_secret="s", run_scheduler=False, standard_price_pesewas=2550,
                        premium_price_pesewas=7500, standard_days=14, premium_days=31, database_path=str(tmp_path / "unused.db"),
                        premium_enabled=True)
    client = create_app(settings, bot=bot, run_async=False).test_client()

    home = client.get("/").get_data(as_text=True)
    assert "English or Twi" in home and "GHS 25.50" in home and "GHS 75" in home and "14 days" in home and "31 days" in home
    assert "https://wa.me/233201234567?text=" in home
    for link in ("/how-it-works", "/pricing", "/privacy", "/terms", "/data-deletion"):
        assert f'href="{link}"' in home

    pricing = client.get("/pricing").get_data(as_text=True)
    assert "GHS 25.50" in pricing and "GHS 75" in pricing and "for 14 days" in pricing and "wa.me/233201234567" in pricing
    assert "SMS backup up to 3 times" in pricing
    how = client.get("/how-it-works").get_data(as_text=True)
    assert "vivid description" in how and "SMS" in how and "Missed" in how


def test_website_uses_vivid_number_and_default_prices(env, monkeypatch):
    client, _, _ = env
    monkeypatch.delenv("WHATSAPP_PUBLIC_NUMBER", raising=False)
    assert "https://wa.me/233506281109?text=Hi%20VIVID" in client.get("/").get_data(as_text=True)
    pricing = client.get("/pricing").get_data(as_text=True)
    assert "GHS 30</p>" in pricing and "GHS 70</p>" in pricing


def test_logo_files_are_served(env):
    client, _, _ = env
    for path in ("/logo.png", "/logo-256.png", "/logo-64.png", "/favicon.ico"):
        response = client.get(path)
        assert response.status_code == 200 and response.data[:8] == b"\x89PNG\r\n\x1a\n"
        response.close()
    assert client.get("/logo-999.png").status_code == 404


def test_standard_plan_gets_no_sms_backup(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)                      # Standard by default
    create_reminder(client)
    make_due(bot)
    wa.fail = True                                      # WhatsApp can't deliver at all
    bot.tick()
    wa.fail = False
    age_fired(bot, 60)
    bot.tick()
    assert wa.sms.sent == []


def test_nudges_repeat_until_done(env):
    client, bot, wa = env
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    bot.tick()
    status_update(client, f"wamid.out.{len(wa.sent)}", "delivered")
    sent_before = len(wa.sent)
    bot.tick()
    assert len(wa.sent) == sent_before                  # not yet: nudge interval is 10 minutes

    def age_last_sent(minutes):
        bot.db._exec("UPDATE reminders SET last_sent_at = ?", (iso(utcnow() - timedelta(minutes=minutes)),))

    age_last_sent(11)
    bot.tick()
    assert "nudge" in wa.last_text() and "Time to call mom" in wa.last_text()
    assert bot.db.get_reminder(1)["nudge_count"] == 1
    webhook(client, text_msg("done"))
    assert bot.db.get_reminder(1)["outcome"] == "done"
    after_done = len(wa.sent)
    age_last_sent(30)
    bot.tick()
    assert len(wa.sent) == after_done                   # no more nudges once Done


def test_nudges_stop_after_max_repeats(env):
    client, bot, wa = env
    bot.nudge_max = 2
    bot.extend_subscription(PHONE)
    create_reminder(client)
    make_due(bot)
    bot.tick()
    status_update(client, f"wamid.out.{len(wa.sent)}", "delivered")
    for _ in range(5):
        bot.db._exec("UPDATE reminders SET last_sent_at = ?", (iso(utcnow() - timedelta(minutes=11)),))
        bot.tick()
    assert bot.db.get_reminder(1)["nudge_count"] == 2


def test_status_shows_plan_and_upgrade_offer(env, monkeypatch):
    client, bot, wa = env
    monkeypatch.setattr(bot.payments, "create_checkout", lambda phone, plan: ("ref-up", "https://pay.example/up"))
    bot.extend_subscription(PHONE)
    webhook(client, text_msg("status"))
    assert "*Standard* subscription" in wa.last_text() and "Reply *premium*" in wa.last_text()
    webhook(client, text_msg("upgrade"))
    assert "Premium" in wa.last_text() and "https://pay.example/up" in wa.last_text()


def test_admin_can_grant_premium(env):
    client, bot, _ = env
    r = client.post("/admin/subscribers", json={"phone": PHONE, "days": 7, "plan": "premium"},
                    headers={"X-Admin-Token": "admin-token"})
    assert r.status_code == 200 and r.get_json()["plan"] == "premium"
    assert bot.plan_of(bot.db.get_user(PHONE)) == "premium"
    bad = client.post("/admin/subscribers", json={"phone": PHONE, "plan": "gold"},
                      headers={"X-Admin-Token": "admin-token"})
    assert bad.status_code == 400


def test_launch_mode_offers_standard_only(tmp_path, monkeypatch):
    wa = FakeWhatsApp()
    bot = VividBot(
        db=Database(str(tmp_path / "launch.db")), whatsapp=wa, ai=FakeAI(), transcriber=FakeASR(),
        payments=Paystack("sk_test_secret"), sms=FakeSMS(), audio_dir=str(tmp_path / "audio"),
        premium_enabled=False,
    )
    monkeypatch.setattr(bot.payments, "create_checkout", lambda phone, plan: (f"ref-{plan.key}", f"https://pay.example/{plan.key}"))
    bot.handle_message(text_msg("hi"))
    menu = wa.last_text()
    assert "Standard*: GHS 30 for 20 days" in menu and "Reply *1*" in menu and "Premium" not in menu
    bot.handle_message(text_msg("2"))
    assert "coming soon" in wa.last_text()
    bot.handle_message(text_msg("1"))
    assert "https://pay.example/standard" in wa.last_text()
    bot.extend_subscription(PHONE)
    bot.handle_message(text_msg("status"))
    assert "*Standard* subscription" in wa.last_text() and "premium" not in wa.last_text().lower()
    bot.handle_message(text_msg("upgrade"))
    assert "coming soon" in wa.last_text()


def test_launch_mode_website_shows_premium_coming_soon(tmp_path, monkeypatch):
    monkeypatch.delenv("PREMIUM_ENABLED", raising=False)
    settings = Settings(verify_token="v", app_secret="s", run_scheduler=False, database_path=str(tmp_path / "unused.db"))
    assert settings.premium_enabled is False
    bot = VividBot(
        db=Database(str(tmp_path / "site.db")), whatsapp=FakeWhatsApp(), ai=FakeAI(), transcriber=FakeASR(),
        payments=Paystack("sk_test_secret"), audio_dir=str(tmp_path / "audio"), premium_enabled=False,
    )
    client = create_app(settings, bot=bot, run_async=False).test_client()
    pricing = client.get("/pricing").get_data(as_text=True)
    assert "GHS 30</p>" in pricing and "for 20 days" in pricing and "Coming soon" in pricing and "GHS 70" not in pricing
    home = client.get("/").get_data(as_text=True)
    assert "coming soon" in home and "SMS backup (Premium)" not in home
