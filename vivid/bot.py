"""VIVID conversation flow and reminder delivery.

Creating a reminder (What + When + Who):
  1. Casual message (text or voice):  "Remind me to call driver Kwame on Friday 1pm"
  2. VIVID asks for the vivid description.
  3. Vivid description (text or voice): "...to tell him to go and service the truck after his trip"

When it is due:
  - WhatsApp first: the reporting-form text ("Time to call driver Kwame to ask him to ...")
    or the subscriber's own voice note, with a ✅ Done button.
  - If WhatsApp hasn't reached the phone within SMS_FALLBACK_MINUTES (phone off / no data),
    or the WhatsApp send fails, the same reminder goes out by SMS.
  - Not marked Done within MISSED_AFTER_MINUTES -> Missed.
  - "list" shows Upcoming / Done / Missed.
"""

import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from . import BOT_NAME, PRODUCT_NAME
from .ai import AIError, ReminderAI
from .db import Database, iso, parse_iso, utcnow
from .payments import Paystack
from .plans import PREMIUM, STANDARD, build_plans, parse_choice
from .sms import ArkeselSMS
from .speech import Transcriber
from .whatsapp import WhatsApp

log = logging.getLogger(__name__)

# WhatsApp only allows free-form messages within 24h of the user's last message.
SERVICE_WINDOW = timedelta(hours=23, minutes=50)
HISTORY_DAYS = 7

HELP_WORDS = {"help", "menu", "start", "hi", "hello", "hey", "boa me", "mmoa"}
LIST_WORDS = {"list", "my reminders", "reminders", "history"}
SUBSCRIBE_WORDS = {"subscribe", "pay", "renew", "status", "subscription", "plan", "my plan"}
UPGRADE_WORDS = {"premium", "upgrade", "go premium"}
CANCEL_DRAFT_WORDS = {"cancel", "stop", "gyae"}
DELETE_WORDS = {"delete my data", "delete my account", "delete me"}
DONE_WORDS = {"done", "✅", "ok done", "finished", "mawie", "mayɛ"}
CANCEL_RE = re.compile(r"^(?:cancel|delete|remove)\s*#?\s*(\d+)$", re.IGNORECASE)
DONE_RE = re.compile(r"^done\s*#?\s*(\d+)$", re.IGNORECASE)


def fmt_time(dt: datetime) -> str:
    hour = dt.strftime("%I").lstrip("0") or "12"
    return f"{dt:%a %d %b} at {hour}:{dt:%M} {dt:%p}"


class VividBot:
    def __init__(
        self,
        db: Database,
        whatsapp: WhatsApp,
        ai: ReminderAI,
        transcriber: Transcriber,
        payments: Paystack,
        sms: ArkeselSMS | None = None,
        tz: str = "Africa/Accra",
        audio_dir: str = "data/audio",
        template_name: str = "vivid_reminder",
        template_lang: str = "en",
        plans: dict | None = None,
        sms_schedule_minutes: tuple = (5, 15, 30),
        nudge_interval_minutes: int = 10,
        nudge_max_repeats: int = 6,
        missed_after_minutes: int = 120,
        owner_numbers: frozenset | set | tuple = (),
    ):
        self.db = db
        self.wa = whatsapp
        self.ai = ai
        self.asr = transcriber
        self.payments = payments
        self.sms = sms or ArkeselSMS("")
        self.tz = ZoneInfo(tz)
        self.audio_dir = Path(audio_dir)
        self.template_name = template_name
        self.template_lang = template_lang
        self.plans = plans or build_plans(3000, 7000, 30, 3)
        self.sms_schedule = [timedelta(minutes=m) for m in sms_schedule_minutes] or [timedelta(minutes=5)]
        self.nudge_interval = timedelta(minutes=nudge_interval_minutes)
        self.nudge_max = nudge_max_repeats
        self.missed_after = timedelta(minutes=missed_after_minutes)
        self.owner_numbers = frozenset(owner_numbers)
        self._locks: defaultdict[str, Lock] = defaultdict(Lock)

    # ------------------------------------------------------------------ inbound
    def handle_webhook(self, payload: dict) -> None:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    try:
                        self.handle_status(status)
                    except Exception:
                        log.exception("Failed to handle status %s", status.get("id"))
                names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
                for message in value.get("messages", []):
                    try:
                        self.handle_message(message, names.get(message.get("from")))
                    except Exception:
                        log.exception("Failed to handle message %s", message.get("id"))

    def handle_status(self, status: dict) -> None:
        """WhatsApp tells us when a message reached the phone (delivered) or was read."""
        reminder = self.db.record_delivery(status.get("id", ""), status.get("status", ""))
        if reminder and status.get("status") == "failed":
            log.warning("WhatsApp delivery failed for reminder %s: %s", reminder["id"], status.get("errors"))
            self._send_sms(reminder)

    def handle_message(self, msg: dict, name: str | None = None) -> None:
        phone = msg["from"]
        if not self.db.mark_processed(msg["id"]):
            return
        with self._locks[phone]:
            self._handle(phone, msg, name)

    def _handle(self, phone: str, msg: dict, name: str | None) -> None:
        user = self.db.get_or_create_user(phone, name)
        self.db.touch_inbound(phone)
        kind = msg.get("type")

        if kind in ("button", "interactive"):
            self._handle_button(phone, self._button_id(msg))
            return

        # A reply opens the 24h window, so voice reminders that fired outside it can now play.
        self._deliver_awaiting(phone, voice_only=True)

        text = (msg.get("text") or {}).get("body", "").strip() if kind == "text" else ""
        command = " ".join(text.lower().split())

        # Data deletion works for everyone, subscribed or not.
        if user["state"] == "confirm_delete":
            if command == "delete all":
                self._delete_everything(phone)
            else:
                self.db.set_state(phone, "idle")
                self.say(phone, "Okay, nothing was deleted. 👍")
            return
        if command in DELETE_WORDS:
            self.db.set_state(phone, "confirm_delete")
            self.say(
                phone,
                "⚠️ This permanently deletes everything VIVID holds about you: your profile, all reminders "
                "(upcoming and past) and your saved voice notes. Any remaining subscription time is lost.\n\n"
                "Reply *DELETE ALL* to confirm, or anything else to cancel.",
            )
            return

        if not self.is_subscribed(user):
            choice = parse_choice(command)
            if choice:
                self._send_checkout(phone, choice)
            else:
                self._send_subscribe(phone, first_time=user["subscribed_until"] is None)
            return

        if kind not in ("text", "audio"):
            self.say(phone, "I can only read text messages and voice notes. 🙏")
            return

        if command in SUBSCRIBE_WORDS:
            if phone in self.owner_numbers:
                self.say(phone, f"✅ You have owner access to {PRODUCT_NAME} (all Premium features): no subscription needed.")
                return
            plan = self.plans[self.plan_of(user)]
            until = parse_iso(user["subscribed_until"]).astimezone(self.tz)
            upsell = ""
            if plan.key == STANDARD:
                premium = self.plans[PREMIUM]
                upsell = (f"\n\nWant SMS backup when WhatsApp can't reach you? Reply *premium* to upgrade "
                          f"({premium.price_text} for {premium.days} days).")
            self.say(phone, f"✅ Your *{plan.name}* subscription is active until {fmt_time(until)}.{upsell}")
            return
        if command in UPGRADE_WORDS:
            self._send_checkout(phone, PREMIUM)
            return
        if command in LIST_WORDS:
            self._send_list(phone)
            return
        if match := CANCEL_RE.match(command):
            ok = self.db.cancel_reminder(phone, int(match.group(1)))
            self.say(phone, "🗑️ Reminder cancelled." if ok else "I couldn't find that upcoming reminder. Reply *list* to see them.")
            return
        if match := DONE_RE.match(command):
            self._mark_done(phone, int(match.group(1)))
            return
        if command in DONE_WORDS and user["state"] == "idle":
            latest = self.db.latest_open(phone)
            if latest:
                self._mark_done(phone, latest["id"])
            else:
                self.say(phone, "There's no reminder waiting to be marked done. Reply *list* to see yours.")
            return
        if command in CANCEL_DRAFT_WORDS and user["state"] != "idle":
            self.db.set_state(phone, "idle")
            self.say(phone, "Okay, I've discarded that reminder.")
            return
        if command in HELP_WORDS and user["state"] == "idle":
            self._send_help(phone, user.get("name"))
            return

        state = user["state"]
        if state == "awaiting_vivid":
            self._receive_vivid(phone, msg, user["draft"] or {})
        elif state == "awaiting_time":
            self._receive_time(phone, msg, user["draft"] or {})
        else:
            self._receive_casual(phone, msg)

    @staticmethod
    def _button_id(msg: dict) -> str:
        if msg.get("type") == "button":  # template quick-reply
            return (msg.get("button") or {}).get("payload", "")
        interactive = msg.get("interactive") or {}
        return (interactive.get("button_reply") or {}).get("id", "")

    def _handle_button(self, phone: str, button_id: str) -> None:
        action, _, raw_id = button_id.partition(":")
        if not raw_id.isdigit():
            self._deliver_awaiting(phone, voice_only=True)
            return
        reminder_id = int(raw_id)
        if action == "done":
            self._mark_done(phone, reminder_id)
        elif action == "open":
            reminder = self.db.get_reminder(reminder_id)
            if reminder and reminder["phone"] == phone:
                try:
                    self.db.link_message(self._deliver(reminder), reminder_id)
                    if reminder["status"] == "awaiting_play":
                        self.db.set_reminder_status(reminder_id, "sent")
                except Exception:
                    log.exception("Could not open reminder %s", reminder_id)
                    self.say(phone, "Sorry, I couldn't load that reminder. 😕")

    def _delete_everything(self, phone: str) -> None:
        for path in self.db.delete_user_data(phone):
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                log.exception("Could not delete voice note %s", path)
        log.info("Deleted all data for a subscriber on request")
        self.say(phone, "🗑️ Done. All your VIVID data has been deleted. Message me any time to start again.")

    def _mark_done(self, phone: str, reminder_id: int) -> None:
        if self.db.set_outcome(phone, reminder_id, "done"):
            self.say(phone, f"✅ Well done! Reminder #{reminder_id} marked as *Done*.")
        else:
            self.say(phone, "I couldn't find that reminder. Reply *list* to see yours.")

    # Step 1: casual message (What + When + Who)
    def _receive_casual(self, phone: str, msg: dict) -> None:
        if msg["type"] == "audio":
            audio_text = self._transcribe(msg)
            if not audio_text:
                self.db.set_state(phone, "awaiting_time", {"task": "", "who": "", "casual_kind": "voice"})
                self.say(phone, "🎙️ Got your voice note. What time should I remind you? Type it, e.g. *6:30pm today*.")
                return
            text = audio_text
        else:
            text = msg["text"]["body"]

        try:
            result = self.ai.understand(text, self.now_local())
        except AIError:
            log.exception("understand failed")
            self.say(phone, "Sorry, I'm having trouble right now. Please try again in a minute. 🙏")
            return

        if not result.is_reminder:
            self.say(phone, "Tell me what to remind you about and when, e.g. *Remind me to call driver Kwame on Friday 1pm*. Reply *help* for more.")
            return

        draft = {
            "task": result.task, "who": result.who, "casual_text": text,
            "casual_kind": msg["type"], "language": result.language,
        }
        due = self._to_utc(result.due_local)
        if due is None:
            self.db.set_state(phone, "awaiting_time", draft)
            self.say(phone, f"⏰ What time should I remind you{' to ' + result.task if result.task else ''}?")
            return
        self._ask_for_vivid(phone, draft, due)

    # Step 1b: the user still owes us a time
    def _receive_time(self, phone: str, msg: dict, draft: dict) -> None:
        text = self._transcribe(msg) if msg["type"] == "audio" else msg["text"]["body"]
        if not text:
            self.say(phone, "I couldn't catch the time from the voice note. Please type it, e.g. *6:30pm*.")
            return
        try:
            result = self.ai.understand(text, self.now_local())
        except AIError:
            log.exception("understand failed")
            self.say(phone, "Sorry, I'm having trouble right now. Please send the time again in a minute.")
            return
        due = self._to_utc(result.due_local)
        if due is None:
            self.say(phone, "I didn't get a time. Please send it like *6:30pm*, *tomorrow 8am* or *Friday 14:00*.")
            return
        if not draft.get("task") and result.task:
            draft["task"] = result.task
        if not draft.get("who") and result.who:
            draft["who"] = result.who
        self._ask_for_vivid(phone, draft, due)

    def _ask_for_vivid(self, phone: str, draft: dict, due) -> None:
        if due <= utcnow() + timedelta(seconds=30):
            self.db.set_state(phone, "awaiting_time", draft)
            self.say(phone, "That time has already passed. ⏳ Please send a time in the future.")
            return
        draft["due_at"] = iso(due)
        self.db.set_state(phone, "awaiting_vivid", draft)
        who = f"\n👤 Who: {draft['who']}" if draft.get("who") else ""
        self.say(
            phone,
            f"📝 What: *{draft.get('task') or 'your reminder'}*\n"
            f"🕐 When: {fmt_time(due.astimezone(self.tz))}{who}\n\n"
            "✨ Now give me the *vivid description*: type it or send a voice note with the full details.\n"
            "_e.g. Remind me to call driver Kwame to tell him to go and service the truck after his trip._\n\n"
            "Reply *cancel* to discard.",
        )

    # Step 2: vivid description
    def _receive_vivid(self, phone: str, msg: dict, draft: dict) -> None:
        task = draft.get("task") or "your reminder"
        due = parse_iso(draft["due_at"])
        audio_path = audio_mime = None

        if msg["type"] == "audio":
            try:
                content, audio_mime = self.wa.download_media(msg["audio"]["id"])
            except Exception:
                log.exception("Could not download vivid voice note")
                self.say(phone, "I couldn't receive that voice note. 😕 Please send it again, or type the description.")
                return
            audio_path = self._save_audio(content, audio_mime)
            vivid_text = self.asr.transcribe(content, audio_mime, draft.get("language", "tw")) if self.asr.enabled else None
            vivid_kind = "voice"
        else:
            vivid_text = msg["text"]["body"]
            vivid_kind = "text"

        reminder_text = f"Time to {task}." if draft.get("language") != "tw" else f"Bere aso: {task}."
        if vivid_text:
            try:
                reminder_text = self.ai.rewrite(vivid_text, task)
            except AIError:
                log.exception("rewrite failed; using fallback text")
                if vivid_kind == "text":
                    reminder_text = vivid_text

        reminder_id = self.db.add_reminder(
            phone=phone,
            task=task,
            who=draft.get("who") or None,
            casual_text=draft.get("casual_text"),
            vivid_kind=vivid_kind,
            vivid_text=vivid_text,
            reminder_text=reminder_text,
            audio_path=audio_path,
            audio_mime=audio_mime,
            due_at=iso(due),
        )
        self.db.set_state(phone, "idle")
        how = "play your voice note back to you" if vivid_kind == "voice" else "remind you"
        self.say(
            phone,
            f"✅ Saved! I'll {how} on {fmt_time(due.astimezone(self.tz))}.\n\n"
            f"Reminder #{reminder_id}. Reply *list* to see all, or *cancel {reminder_id}* to cancel it.",
        )

    # ----------------------------------------------------------------- outbound
    def tick(self) -> int:
        """One scheduler pass: fire due reminders, repeat unanswered ones (nudge), send Premium SMS
        backups for undelivered ones, and mark old ones Missed."""
        fired = self.fire_due()
        self.send_nudges()
        self.send_sms_fallbacks()
        self.db.sweep_missed(utcnow() - self.missed_after)
        return fired

    def fire_due(self) -> int:
        reminders = self.db.claim_due(utcnow())
        for reminder in reminders:
            with self._locks[reminder["phone"]]:
                self._fire(reminder)
        return len(reminders)

    def _send_out(self, r: dict, again: bool = False) -> tuple[str | None, str]:
        """Sends a reminder on WhatsApp; returns (message id, new status)."""
        user = self.db.get_user(r["phone"]) or {}
        last = parse_iso(user.get("last_inbound_at"))
        if last is not None and utcnow() - last < SERVICE_WINDOW:
            return self._deliver(r, again=again), "sent"
        # Outside the 24h window only an approved template may be sent.
        wamid = self.wa.send_template(
            r["phone"], self.template_name, self.template_lang, [r["reminder_text"]], button_payload=f"open:{r['id']}"
        )
        return wamid, ("awaiting_play" if r["vivid_kind"] == "voice" else "sent")

    def _fire(self, r: dict) -> None:
        try:
            wamid, status = self._send_out(r)
            self.db.set_reminder_status(r["id"], status)
            self.db.link_message(wamid, r["id"])
        except Exception as exc:
            log.exception("WhatsApp reminder %s failed; falling back to SMS", r["id"])
            self.db.set_reminder_status(r["id"], "failed", str(exc)[:500])
            self._send_sms(self.db.get_reminder(r["id"]))

    def _deliver(self, r: dict, again: bool = False) -> str | None:
        """Sends the full reminder on WhatsApp with a Done button; returns the main message id."""
        done = [(f"done:{r['id']}", "✅ Done")]
        heading = f"👉 *{BOT_NAME}* nudge: you haven't tapped Done yet" if again else f"⏰ *{BOT_NAME}*"
        if r["vivid_kind"] == "voice" and r["audio_path"] and Path(r["audio_path"]).exists():
            self.wa.send_text(r["phone"], f"{heading}: here is your voice reminder 🎙️")
            content = Path(r["audio_path"]).read_bytes()
            media_id = self.wa.upload_media(content, r["audio_mime"] or "audio/ogg")
            wamid = self.wa.send_audio(r["phone"], media_id)
            self.wa.send_buttons(r["phone"], "Tap *Done* when you've done it.", done)
            return wamid
        return self.wa.send_buttons(
            r["phone"], f"{heading}\n\n{r['reminder_text']}\n\nTap *Done* when you've done it.", done
        )

    def _deliver_awaiting(self, phone: str, voice_only: bool = True) -> bool:
        pending = [r for r in self.db.awaiting_play(phone) if not voice_only or r["vivid_kind"] == "voice"]
        for r in pending:
            try:
                self.db.link_message(self._deliver(r), r["id"])
                self.db.set_reminder_status(r["id"], "sent")
            except Exception as exc:
                log.exception("Could not play reminder %s", r["id"])
                self.db.set_reminder_status(r["id"], "failed", str(exc)[:500])
        return bool(pending)

    def send_nudges(self) -> int:
        """Re-sends reminders that reached the phone but aren't Done yet, every nudge interval."""
        count = 0
        for r in self.db.nudge_due(utcnow() - self.nudge_interval, self.nudge_max):
            with self._locks[r["phone"]]:
                if not self.db.claim_nudge(r["id"], r["nudge_count"]):
                    continue
                try:
                    wamid, _ = self._send_out(r, again=True)
                    self.db.link_message(wamid, r["id"])
                    count += 1
                except Exception:
                    log.exception("Could not repeat reminder %s", r["id"])
        return count

    def _sms_allowance(self, phone: str) -> int:
        user = self.db.get_user(phone) or {"phone": phone}
        return min(self.plans[self.plan_of(user)].sms_backups, len(self.sms_schedule))

    def send_sms_fallbacks(self) -> int:
        """Premium: SMS reminders WhatsApp hasn't delivered, on the SMS schedule (e.g. 5, 15, 30 min)."""
        now, count = utcnow(), 0
        for r in self.db.undelivered_open(len(self.sms_schedule)):
            sent = r.get("sms_count") or 0
            if sent >= self._sms_allowance(r["phone"]):
                continue
            immediate = sent == 0 and r.get("delivery") == "failed"
            if not immediate and now - parse_iso(r["fired_at"]) < self.sms_schedule[sent]:
                continue
            count += self._send_sms(r)
        return count

    def _send_sms(self, r: dict | None) -> bool:
        if not r or not self.sms.enabled:
            return False
        sent = r.get("sms_count") or 0
        allowed = self._sms_allowance(r["phone"])
        if sent >= allowed or not self.db.claim_sms(r["id"], sent):
            return False
        text = f"{BOT_NAME}: {r['reminder_text']}"
        if r["vivid_kind"] == "voice":
            text += " (Your voice note is waiting on WhatsApp.)"
        if sent:
            text += f" [reminder {sent + 1} of {allowed}]"
        if self.sms.send(r["phone"], text):
            log.info("SMS backup %s/%s sent for reminder %s", sent + 1, allowed, r["id"])
            return True
        self.db.release_sms(r["id"])  # try again on the next tick
        return False

    # ------------------------------------------------------------ subscriptions
    def plan_of(self, user: dict) -> str:
        if user.get("phone") in self.owner_numbers:
            return PREMIUM
        return user.get("plan") if user.get("plan") in self.plans else STANDARD

    def is_subscribed(self, user: dict) -> bool:
        if user.get("phone") in self.owner_numbers:
            return True
        until = parse_iso(user.get("subscribed_until"))
        return until is not None and until > utcnow()

    def extend_subscription(self, phone: str, days: int | None = None, plan: str = STANDARD) -> datetime:
        plan = plan if plan in self.plans else STANDARD
        user = self.db.get_or_create_user(phone)
        current = parse_iso(user.get("subscribed_until"))
        start = current if current and current > utcnow() else utcnow()
        until = start + timedelta(days=days or self.plans[plan].days)
        self.db.set_subscribed_until(phone, until, plan)
        return until

    def _plan_menu(self) -> str:
        std, pre = self.plans[STANDARD], self.plans[PREMIUM]
        return (
            f"1️⃣ *{std.name}*: {std.price_text} for {std.days} days\n"
            "   Reminders on WhatsApp, repeated until you tap Done\n"
            f"2️⃣ *{pre.name}*: {pre.price_text} for {pre.days} days\n"
            f"   Everything in {std.name} + SMS backup (up to {pre.sms_backups}x) when WhatsApp can't reach you\n\n"
            "Reply *1* or *2* to get your payment link (mobile money or card)."
        )

    def _send_subscribe(self, phone: str, first_time: bool) -> None:
        intro = (
            f"👋 Welcome to *{BOT_NAME}*! I remind you of your plans at exactly the right time, "
            "in English or Twi, by text or voice note."
            if first_time
            else f"Your *{PRODUCT_NAME}* subscription has expired."
        )
        self.say(phone, f"{intro}\n\nChoose a {PRODUCT_NAME} plan:\n{self._plan_menu()}")

    def _send_checkout(self, phone: str, plan_key: str) -> None:
        plan = self.plans[plan_key]
        if self.payments.enabled:
            try:
                reference, url = self.payments.create_checkout(phone, plan)
                self.db.add_payment(reference, phone, plan.key)
                self.say(phone, f"💳 *{PRODUCT_NAME} {plan.name}*: {plan.price_text} for {plan.days} days.\n"
                                f"Pay here:\n{url}\n\nI'll message you as soon as payment is confirmed.")
                return
            except Exception:
                log.exception("Could not create checkout")
        self.say(phone, f"*{PRODUCT_NAME} {plan.name}* ({plan.price_text} for {plan.days} days): payment is "
                        "temporarily unavailable. Please try again later. 🙏")

    def confirm_payment(self, reference: str) -> bool:
        result = self.db.complete_payment(reference)
        if not result:
            return False
        phone, plan_key = result
        until = self.extend_subscription(phone, plan=plan_key)
        plan = self.plans.get(plan_key, self.plans[STANDARD])
        try:
            self.wa.send_text(
                phone,
                f"🎉 Payment received! *{PRODUCT_NAME} {plan.name}* is active until "
                f"{fmt_time(until.astimezone(self.tz))}.\n\nTry it now: *Remind me to call mom at 6:30pm*",
            )
        except Exception:
            log.exception("Could not send payment confirmation")
        return True

    # ------------------------------------------------------------------ helpers
    def say(self, phone: str, text: str) -> None:
        self.wa.send_text(phone, text)

    def now_local(self) -> datetime:
        return utcnow().astimezone(self.tz)

    def _to_utc(self, due_local: str):
        if not due_local:
            return None
        try:
            naive = datetime.fromisoformat(due_local.strip())
        except ValueError:
            return None
        local = naive.replace(tzinfo=self.tz) if naive.tzinfo is None else naive
        return local.astimezone(utcnow().tzinfo)

    def _transcribe(self, msg: dict) -> str | None:
        if not self.asr.enabled:
            return None
        try:
            content, mime = self.wa.download_media(msg["audio"]["id"])
        except Exception:
            log.exception("Could not download voice note")
            return None
        return self.asr.transcribe(content, mime)

    def _save_audio(self, content: bytes, mime: str) -> str:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        ext = {"audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/amr": ".amr"}.get(
            mime.split(";")[0].strip(), ".ogg"
        )
        path = self.audio_dir / f"{uuid.uuid4().hex}{ext}"
        path.write_bytes(content)
        return str(path)

    def _line(self, r: dict, when_field: str = "due_at") -> str:
        icon = "🎙️" if r["vivid_kind"] == "voice" else "📝"
        who = f" ({r['who']})" if r.get("who") and r["who"].lower() not in r["task"].lower() else ""
        when = fmt_time(parse_iso(r[when_field]).astimezone(self.tz))
        return f"#{r['id']} {icon} {when}: {r['task']}{who}"

    def _send_list(self, phone: str) -> None:
        upcoming = self.db.pending_reminders(phone)
        finished = self.db.finished_since(phone, utcnow() - timedelta(days=HISTORY_DAYS))
        done = [r for r in finished if r.get("outcome") == "done"]
        missed = [r for r in finished if r.get("outcome") == "missed"]
        waiting = [r for r in finished if not r.get("outcome")]

        if not (upcoming or done or missed or waiting):
            self.say(phone, "You have no reminders yet. Send one like *Remind me to pray at 5am*.")
            return

        def section(title: str, items: list[dict], empty: str, field: str = "due_at") -> list[str]:
            lines = [title]
            lines += [self._line(r, field) for r in items[:10]] or [f"   {empty}"]
            return lines + [""]

        lines = []
        if waiting:
            lines += section("⏳ *Due now* (tap Done or reply *done*)", waiting, "")
        lines += section("🔜 *Upcoming*", upcoming, "none")
        lines += section(f"✅ *Done* (last {HISTORY_DAYS} days)", done, "none")
        lines += section(f"❌ *Missed* (last {HISTORY_DAYS} days)", missed, "none")
        lines.append("Reply *cancel <number>* to cancel an upcoming one, or *done <number>* to mark one done.")
        self.say(phone, "\n".join(lines))

    def _send_help(self, phone: str, name: str | None) -> None:
        hello = f"Hi {name.split()[0]}! " if name else "Hi! "
        self.say(
            phone,
            f"{hello}I'm *{BOT_NAME}* ✨\n\n"
            "1️⃣ Tell me *what*, *when* and *who* (type or voice note, English or Twi):\n"
            "   _Remind me to call driver Kwame on Friday 1pm_\n"
            "2️⃣ I'll ask for the *vivid description* with all the details.\n"
            "3️⃣ At that time I send it to you on WhatsApp, and keep nudging you until you tap *✅ Done*.\n"
            "   On Premium, if your phone is offline, I also text you by SMS (up to 3 times).\n\n"
            "Commands: *list* (Upcoming / Done / Missed) · *done* · *cancel 3* · *status* · *premium* · *delete my data*",
        )
