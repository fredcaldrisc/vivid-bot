"""Public pages Meta asks for before an app can be published:
privacy policy, terms of service and data-deletion instructions."""

import os
from html import escape

from . import BOT_NAME, PRODUCT_NAME

UPDATED = "7 November 2026"


def _contact_line() -> str:
    email = os.environ.get("CONTACT_EMAIL", "").strip()
    whatsapp = f"send a WhatsApp message to {BOT_NAME}"
    if email:
        return f'{whatsapp}, or email <a href="mailto:{escape(email)}">{escape(email)}</a>'
    return whatsapp


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · {BOT_NAME}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 720px;
         margin: 0 auto; padding: 24px 16px 48px; line-height: 1.6; color: #1d1d1f; background: #fff; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
  .updated {{ color: #666; margin-top: 4px; }} a {{ color: #0b6bcb; }}
  nav {{ margin-top: 2.5rem; font-size: .95rem; }} nav a {{ margin-right: 1rem; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #111; color: #eee; }} .updated {{ color: #aaa; }}
                                         a {{ color: #6cb4ff; }} }}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="updated">{BOT_NAME} ({PRODUCT_NAME}) · Last updated {UPDATED}</p>
{body}
<nav><a href="/privacy">Privacy policy</a><a href="/terms">Terms of service</a><a href="/data-deletion">Delete your data</a></nav>
</body></html>"""


def privacy_page() -> str:
    return _page("Privacy policy", f"""
<p>{BOT_NAME} is a WhatsApp reminder assistant. This page explains what we collect, why, and how you can delete it.</p>

<h2>What we collect</h2>
<ul>
  <li><b>Your WhatsApp number and profile name</b>, to know who a reminder belongs to and reply to you.</li>
  <li><b>Your reminders</b>: the messages you send (what, when, who) and the vivid description, as text or voice notes.</li>
  <li><b>Voice notes</b> you send as reminders, so we can play them back to you at the right time.</li>
  <li><b>Delivery and status information</b>: whether a reminder was delivered, read, marked Done or Missed.</li>
  <li><b>Subscription and payment records</b>: a payment reference and the dates your subscription is active.
      We never see or store your card or mobile-money details; the payment provider handles those.</li>
</ul>

<h2>How we use it</h2>
<p>Only to run the reminder service: understand your reminder, send it to you on time on WhatsApp
(or by SMS if WhatsApp can't reach your phone), and manage your subscription. We do not sell your data
or use it for advertising.</p>

<h2>Services that process your data for us</h2>
<ul>
  <li><b>Meta (WhatsApp)</b> carries the messages between you and {BOT_NAME}.</li>
  <li><b>Anthropic (Claude)</b> reads the text of your reminders to find the time and write the reminder message.</li>
  <li><b>GhanaNLP</b> may transcribe voice notes (English and Twi) to find the reminder time.</li>
  <li><b>Arkesel</b> sends SMS reminders when WhatsApp can't reach your phone.</li>
  <li><b>Paystack</b> processes subscription payments.</li>
  <li><b>Render</b> hosts the {BOT_NAME} server and its storage.</li>
</ul>

<h2>How long we keep it</h2>
<p>Your reminders and voice notes are kept while you use {BOT_NAME}, so you can see your Done, Missed and
Upcoming list. You can delete everything at any time (see below). Payment references are kept for our
accounting records.</p>

<h2>Deleting your data</h2>
<p>Send <b>delete my data</b> to {BOT_NAME} on WhatsApp and confirm with <b>DELETE ALL</b>. This removes your
profile, all reminders and all saved voice notes straight away. Details: <a href="/data-deletion">Delete your data</a>.</p>

<h2>Contact</h2>
<p>For any privacy question, {_contact_line()}.</p>
""")


def terms_page() -> str:
    return _page("Terms of service", f"""
<p>By using {BOT_NAME} you agree to these terms.</p>
<h2>The service</h2>
<p>{BOT_NAME} sends you reminders you create on WhatsApp, at the time you choose, and by SMS when WhatsApp
can't reach your phone. Access requires an active {PRODUCT_NAME} subscription.</p>
<h2>Reminders are a help, not a guarantee</h2>
<p>We work to deliver every reminder on time, but delivery depends on WhatsApp, mobile networks and your
phone. Do not rely on {BOT_NAME} alone for anything where a missed reminder could cause harm, such as
critical medication timing or emergencies.</p>
<h2>Your content</h2>
<p>You are responsible for the reminders and voice notes you send. Don't use {BOT_NAME} to store anything
unlawful or to harass anyone.</p>
<h2>Subscriptions</h2>
<p>A subscription gives access for the period shown when you pay. You can stop at any time by not renewing.</p>
<h2>Changes</h2>
<p>We may update these terms; the date at the top shows the latest version.</p>
<h2>Contact</h2>
<p>To contact us, {_contact_line()}.</p>
""")


def data_deletion_page() -> str:
    return _page("Delete your data", f"""
<p>You can delete everything {BOT_NAME} holds about you, at any time, from WhatsApp:</p>
<ol>
  <li>Send <b>delete my data</b> to {BOT_NAME}.</li>
  <li>{BOT_NAME} explains what will be deleted. Reply <b>DELETE ALL</b> to confirm.</li>
  <li>Your profile, all reminders (upcoming and past) and all saved voice notes are deleted immediately,
      and {BOT_NAME} confirms on WhatsApp.</li>
</ol>
<p>Payment references are kept for accounting records. If you can't use WhatsApp, {_contact_line()} and we
will delete your data for you.</p>
""")
