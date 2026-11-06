# Taking VIVID live on a Ghanaian Telecel number

Do the steps in this order. Each one depends on the one before it.

## Why the live bot doesn't reply

The version running on your host is the **old code**. It only stored incoming WhatsApp messages in `memory.json` and never sent a reply. Nothing on Meta's side is broken. The fix is to deploy the code in this folder (step 5). The other common causes are listed in step 6 so you can rule them out.

---

## 1. Give yourself access to the WhatsApp account
In **Business settings → Business assets → WhatsApp accounts**, the account **"Fred Caldris C"** shows *0 people*. Click **Give me full access**.
Use this account for VIVID, not "Test WhatsApp Business Account". Meta's test account comes with a US test number that can only message 5 pre-approved phones.

## 2. Prepare the Telecel SIM
- The number must **not** currently be on WhatsApp or WhatsApp Business. If it is, open WhatsApp on that phone → **Settings → Account → Delete my account**, then wait about 10 minutes. Back up any chats you need first. Deleting the account erases them.
- Keep the SIM in a phone that can receive an **SMS or a call**. Meta sends the verification code that way.
- From then on, the number works only through VIVID. You can't use it in the WhatsApp app any more.

## 3. Add the number to Meta
1. Go to **developers.facebook.com → your app → WhatsApp → API Setup** and click **Add phone number**. (Or use **WhatsApp Manager → Phone numbers → Add phone number**.)
2. Choose the **"Fred Caldris C"** WhatsApp account.
3. **Display name: `VIVID`**. Category: *Other* (or *Professional services*). Description: "VIVID reminds you of your plans on time."
4. Country **Ghana (+233)**, then your Telecel number without the leading 0 (e.g. `20 123 4567`). Verify by SMS.
5. Copy the new **Phone number ID**. It goes into `WHATSAPP_PHONE_NUMBER_ID`.
6. In **WhatsApp Manager → Phone numbers → (your number) → Profile**, upload the **VIVID logo** as the profile photo.
7. Meta reviews the display name, usually within 1–2 days. Messages still work while it's pending.

## 4. Account set-up Meta requires
- **Payment method:** WhatsApp Manager → Overview → *Add payment method*. Reminders sent more than 24 h after the user's last message are paid "utility" messages.
- **Business verification:** Business settings → Security center → *Start verification*. Without it you're limited to messaging 250 people a day.
- **Permanent access token:** the token on the API Setup page **expires after 24 hours**. That alone makes a bot go silent. Instead:
  Business settings → **Users → System users → Add** (role *Admin*) → **Assign assets**: your app, plus the "Fred Caldris C" WhatsApp account with full control → **Generate token** with `whatsapp_business_messaging` and `whatsapp_business_management`, expiry **Never**. This is `WHATSAPP_TOKEN`.
- **Reminder template:** WhatsApp Manager → **Message templates → Create** →
  - Category **Utility**, name **`vivid_reminder`**, language **English**
  - Body: `⏰ VIVID reminder: {{1}}` (sample: *Time to call driver Kwame to ask him to service the truck.*)
  - Button: **Quick reply → `Open reminder`**

## 5. Deploy the new code on Render
Update your **existing** Render web service rather than creating a new one. That way the URL Meta already calls stays the same.

**a. Upload the code to GitHub.** Open the repository Render deploys from → **Add file → Upload files** → drag in:
- `app.py`, `requirements.txt`, `Procfile`, `README.md`, `GO_LIVE.md`, `.env.example`, `.gitignore`, `test_app.py`
- the whole **`vivid`** folder and the **`scripts`** folder

**Do not upload** `venv`, `.env` (it holds your secrets), `data` or `memory.json`. Commit to the main branch. Render redeploys automatically. Afterwards, delete the old `memory.json` from the repository if it's there.

**b. Instance type → Starter or higher (paid).** Free Render services go to sleep after 15 minutes without traffic. While asleep the reminder clock stops, so reminders would fire late or not at all. Free services also can't have a disk.

**c. Disks → Add disk:** name `vivid-data`, mount path **`/var/data`**, 1 GB. This keeps reminders and voice notes across deploys. Without it, every deploy wipes them.

**d. Settings:**
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn -w 1 --threads 8 --bind 0.0.0.0:$PORT app:app` (keep **one** worker, because the reminder clock runs inside it)
- Health check path: `/health`

**e. Environment → add variables** (same names as `.env.example`):
- `PYTHON_VERSION` = `3.14.0` (the version VIVID was tested on)
- `DATABASE_PATH` = `/var/data/vivid.db`, `AUDIO_DIR` = `/var/data/audio`
- `VERIFY_TOKEN`, `APP_SECRET` (Meta app → App settings → Basic), `WHATSAPP_TOKEN` (permanent token from step 4), `WHATSAPP_PHONE_NUMBER_ID` (the Telecel one from step 3)
- `ANTHROPIC_API_KEY`, `ARKESEL_API_KEY`, `ADMIN_TOKEN`, `PAYSTACK_SECRET_KEY`
- `PUBLIC_BASE_URL` = your Render URL, e.g. `https://vivid-xxxx.onrender.com`

Save. Render rebuilds, and the **Logs** tab should end with `VIVID scheduler running every 20s`. Open `https://YOUR-RENDER-URL/health`: it should show `{"status":"ok"}`.

## 6. Connect Meta to the deployed bot
1. App → **WhatsApp → Configuration → Webhook**: Callback URL `https://YOUR-DOMAIN/webhook`, Verify token = your `VERIFY_TOKEN` → **Verify and save**.
2. Under **Webhook fields**, subscribe to **`messages`**. This covers incoming texts and the delivered/read statuses the SMS fallback relies on.
3. App dashboard → switch the app from **Development** to **Live**. Meta asks for a privacy-policy URL first.
4. Make sure the app is subscribed to the WhatsApp account. Adding the number through API Setup normally does this. If messages still don't arrive, run:
   ```bash
   curl -X POST "https://graph.facebook.com/v23.0/YOUR_WABA_ID/subscribed_apps" -H "Authorization: Bearer YOUR_WHATSAPP_TOKEN"
   ```

## 7. SMS fallback (Arkesel)
1. Sign up at arkesel.com and top up SMS credit.
2. **Sender IDs → Register `VIVID`**. Approval takes about a day. Until then SMS may fail or show a default sender.
3. Copy your **API key** into `ARKESEL_API_KEY`.
4. How it works: when a reminder fires, VIVID sends it on WhatsApp first. If WhatsApp hasn't reported it as *delivered to the phone* within `SMS_FALLBACK_MINUTES` (default 5), VIVID sends the same reminder by SMS. That covers a phone that's off or has no data. If WhatsApp reports a failure, the SMS goes out straight away.

## 8. Test it
1. Give your own number access (WhatsApp numbers are digits only, e.g. `233241234567`):
   ```bash
   curl -X POST https://YOUR-DOMAIN/admin/subscribers -H "X-Admin-Token: YOUR_ADMIN_TOKEN" -H "Content-Type: application/json" -d "{\"phone\":\"233241234567\",\"days\":30}"
   ```
2. On your personal phone, message the Telecel number: **hi**. VIVID should reply with its help message.
3. Send *Remind me to call driver Kwame in 3 minutes*, then the vivid description. You should get it in reporting form with a **✅ Done** button.
4. For the SMS test, create a reminder for 2 minutes ahead, turn off mobile data, and wait about 7 minutes. The SMS should arrive.
5. Send **list** to see Upcoming / Done / Missed.

If "hi" gets no reply, check the **Logs** tab in Render first. A `401 invalid webhook signature` there means `APP_SECRET` is wrong. If there are no log lines at all, Meta isn't reaching the bot: recheck step 6.
