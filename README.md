# VIVID

A WhatsApp-only AI reminder bot. Subscribers buy **Vivid Reminders**; in chat, the bot is just **VIVID**.

## How it works

1. A subscriber sends **what + when + who** by text or voice note, in English or Twi: *"Remind me to call driver Kwame on Friday 1pm"*.
2. VIVID confirms (What / When / Who) and asks for the **vivid description**.
3. The subscriber sends it: *"…to tell him to go and service the truck after his trip"*.
4. At Friday 1 pm VIVID sends, **on WhatsApp first**:
   - **Typed description:** the reminder in reporting form, *"Time to call driver Kwame to ask him to go and service the truck after his trip."*
   - **Voice note:** the subscriber's own recording, played back.

   Both come with a **✅ Done** button.
5. **SMS fallback:** if WhatsApp hasn't reached the phone within 5 minutes (phone off or no data), or the send fails, VIVID sends the reminder by SMS through Arkesel.
6. **Done / Missed / Upcoming:** tapping Done (or replying `done`) marks it Done. A reminder not marked Done within 2 hours becomes Missed. `list` shows all three.

Reminders always go to the subscriber. "Who" is the person the task involves, and it appears in the reminder text.

Other commands: `list`, `done`, `done 3`, `cancel 3`, `status`, `help`, and `cancel` while a reminder is half-made.
People who haven't subscribed get a payment link instead.

**Going live on the Telecel number:** see [GO_LIVE.md](GO_LIVE.md).

## Code map

| File | Job |
|---|---|
| `app.py` | Flask routes: Meta webhook, Paystack webhook, admin API, scheduler start-up |
| `vivid/bot.py` | Conversation flow, sending reminders, subscriptions |
| `vivid/ai.py` | Claude: reads casual English/Twi messages, rewrites descriptions as "Time to …" |
| `vivid/speech.py` | Speech-to-text for voice notes (GhanaNLP Khaya) |
| `vivid/whatsapp.py` | WhatsApp Cloud API client (text, audio, templates, media) |
| `vivid/payments.py` | Paystack checkout and webhook signatures |
| `vivid/sms.py` | Arkesel SMS fallback |
| `vivid/db.py` | SQLite storage |
| `vivid/scheduler.py` | Background loop that checks for due reminders every 20 s |

## Setup

### 1. WhatsApp (Meta)
1. Create a Meta app with the WhatsApp product at developers.facebook.com and add a business phone number.
2. In WhatsApp Manager, set the profile **display name to "VIVID"** and upload the logo as the profile photo. Meta reviews display names.
3. Create a **permanent System User token** with `whatsapp_business_messaging` permission, and copy the Phone Number ID.
4. **Create the reminder template.** WhatsApp only lets a business send free-form messages within 24 hours of the user's last message. Reminders set for later than that must go out as a pre-approved template. Create a *Utility* template named `vivid_reminder`:
   - Body: `⏰ VIVID reminder: {{1}}`
   - Quick-reply button: `Open reminder`

   Tapping **Open reminder** opens the full reminder with its Done button, and plays the voice note if there is one. Templates can't carry audio.
5. Subscribe the webhook to the **`messages`** field. That one subscription also carries the delivered/read statuses the SMS fallback relies on.

### 2. Claude
Get an API key at console.anthropic.com and set `ANTHROPIC_API_KEY`. The model is `claude-opus-5-5`, run at low effort because these are short extraction jobs.

### 3. Voice notes in Twi (optional, recommended)
Claude can't listen to audio, so voice notes are transcribed only to find the task and the time. The recording itself is what gets replayed. Register at the GhanaNLP developer portal for the **Khaya ASR** API, then set `ASR_URL` and `ASR_KEY`.
> ⚠️ The endpoint format in `.env.example` and the response parsing in `vivid/speech.py` haven't been checked against a live key. Confirm the URL and the accepted audio formats (WhatsApp voice notes are OGG/Opus) in the portal.

Without ASR, voice notes still work: VIVID asks the user to type the time and still plays the vivid voice note back.

### 4. Subscriptions (Paystack)
1. Create a Paystack account (Ghana: cards and mobile money). Use the test secret key first.
2. Set the webhook URL to `https://YOUR-DOMAIN/paystack/webhook`.
3. Set `SUBSCRIPTION_PRICE_PESEWAS` (2000 = GHS 20.00) and `SUBSCRIPTION_DAYS`.

Grant access by hand (for testers or cash payments):
```bash
curl -X POST https://YOUR-DOMAIN/admin/subscribers -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" -d "{\"phone\":\"233241234567\",\"days\":30}"
```

## Run locally

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # then fill it in
venv\Scripts\python app.py
```
Expose port 5000 with a tunnel (e.g. ngrok), then set the Meta callback URL to `https://<tunnel>/webhook` with your `VERIFY_TOKEN`.

## Test

```bash
venv\Scripts\python -m pytest -q
```
The tests use fake WhatsApp, Claude, ASR and SMS clients. They cover subscriptions, the typed and voice flows, Who capture, delivery inside and outside the 24 h window, SMS fallback (timeout, failed send, failed status, no SMS once delivered), Done/Missed/Upcoming, list/cancel, and duplicate webhooks.

## Deploy

Any Python host with a **persistent disk** (Render with a disk, Railway volume, Fly.io volume, or a VPS). Start command: `gunicorn -w 1 --threads 8 app:app`. Keep **one** worker, because the scheduler runs inside it. Put all `.env` values in the host's secret settings.

## Before going big
- Move SQLite and the saved voice notes to Postgres and object storage (e.g. Supabase) so you can run more than one instance.
- Users' voice notes are personal data. Tell subscribers they are stored, and delete them after delivery if you don't need them.
