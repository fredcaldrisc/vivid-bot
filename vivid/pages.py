"""Public pages Meta asks for before an app can be published (privacy policy, terms of service,
data-deletion instructions), plus the shared layout the website uses too."""

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


# Shared look for every public page (website and legal pages). Colours come from the VIVID logo.
CSS = """
  :root { --bg: #ffffff; --fg: #1d1d1f; --muted: #5f5f66; --card: #f5f5f7; --line: #e4e4e8;
          --link: #6b2bd9; --wa: #1f9d55; --grad: linear-gradient(120deg, #ff8a00, #ff2d7a 40%, #8b3dff 70%, #1fa2ff); }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0b0b0d; --fg: #f2f2f4; --muted: #a8a8b3; --card: #17171b; --line: #2a2a31; --link: #b79bff; }
  }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; line-height: 1.6;
         color: var(--fg); background: var(--bg); }
  a { color: var(--link); }
  .wrap { max-width: 760px; margin: 0 auto; padding: 0 16px; }
  header.top { background: #000; }
  header.top .wrap { display: flex; align-items: center; justify-content: space-between; gap: 12px;
                     padding-top: 10px; padding-bottom: 10px; flex-wrap: wrap; }
  header.top .brand { display: flex; align-items: center; gap: 10px; color: #fff; text-decoration: none;
                      font-weight: 700; letter-spacing: .12em; }
  header.top .brand img { width: 36px; height: 36px; border-radius: 8px; }
  header.top nav a { color: #e8e8ee; text-decoration: none; margin-left: 14px; font-size: .95rem; }
  header.top nav a:first-child { margin-left: 0; }
  header.top nav a:hover { color: #fff; text-decoration: underline; }
  main { padding: 24px 0 48px; }
  h1 { font-size: 1.8rem; line-height: 1.25; margin: 0 0 .25rem; }
  h2 { font-size: 1.2rem; margin-top: 2rem; }
  .updated, .muted { color: var(--muted); }
  .hero { background: #000; color: #fff; text-align: center; padding: 32px 0 40px; }
  .hero img { width: 160px; height: 160px; }
  .hero h1 { font-size: 2rem; margin-top: 8px; }
  .hero p { color: #d6d6de; font-size: 1.1rem; max-width: 34em; margin: .5rem auto 1.25rem; }
  .grad { background: var(--grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .btn { display: inline-block; padding: 14px 22px; border-radius: 999px; font-weight: 700; text-decoration: none;
         font-size: 1.05rem; }
  .btn-wa { background: var(--wa); color: #fff; }
  .btn-wa:hover { filter: brightness(1.1); }
  .btn-ghost { color: inherit; border: 1px solid var(--line); margin-left: 8px; }
  .hero .btn-ghost { border-color: #444; color: #fff; }
  .hero .btn { margin-top: 8px; }
  .cards { display: grid; grid-template-columns: 1fr; gap: 12px; padding: 0; list-style: none; }
  @media (min-width: 620px) { .cards { grid-template-columns: 1fr 1fr; } .hero h1 { font-size: 2.4rem; } }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 16px; }
  .card h3 { margin: 0 0 .25rem; font-size: 1.05rem; }
  .card p { margin: 0; color: var(--muted); }
  .steps { padding-left: 1.2rem; } .steps li { margin-bottom: .9rem; }
  .chat { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px;
          font-size: .95rem; }
  .chat .you, .chat .bot { padding: 8px 12px; border-radius: 12px; margin: 6px 0; max-width: 88%; }
  .chat .you { background: #d9fdd3; color: #111; margin-left: auto; }
  .chat .bot { background: var(--bg); border: 1px solid var(--line); }
  .price { text-align: center; background: var(--card); border: 1px solid var(--line); border-radius: 18px;
           padding: 24px 16px; margin: 1.5rem 0; }
  .price .amount { font-size: 2.6rem; font-weight: 800; margin: 0; }
  .price ul { text-align: left; display: inline-block; margin: 1rem 0 1.25rem; }
  .cta { text-align: center; margin: 2.5rem 0 0; }
  footer { border-top: 1px solid var(--line); padding: 20px 0 32px; font-size: .9rem; color: var(--muted); }
  footer a { margin-right: 1rem; display: inline-block; margin-bottom: 6px; }
"""


def _base_url() -> str:
    """Full address of the site (PUBLIC_BASE_URL), so link previews on WhatsApp can find the logo."""
    return os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")


def layout(title: str, main: str, hero: str = "") -> str:
    """Wraps a page in the shared header, footer and styles. `hero` is an optional full-width black band."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · {BOT_NAME}</title>
<meta name="description" content="{BOT_NAME} reminds you on WhatsApp at exactly the right time, in English or Twi, by text or voice note.">
<link rel="icon" type="image/png" href="/logo-64.png">
<meta property="og:title" content="{BOT_NAME} · {PRODUCT_NAME}">
<meta property="og:description" content="WhatsApp reminders in English or Twi, by text or voice note.">
<meta property="og:image" content="{escape(_base_url())}/logo-256.png">
<style>{CSS}</style></head><body>
<header class="top"><div class="wrap">
  <a class="brand" href="/"><img src="/logo-64.png" alt="" width="36" height="36">{BOT_NAME}</a>
  <nav><a href="/how-it-works">How it works</a><a href="/pricing">Pricing</a></nav>
</div></header>
{hero}
<main><div class="wrap">
{main}
</div></main>
<footer><div class="wrap">
  <a href="/">Home</a><a href="/how-it-works">How it works</a><a href="/pricing">Pricing</a>
  <a href="/privacy">Privacy policy</a><a href="/terms">Terms of service</a><a href="/data-deletion">Delete your data</a>
  <div>© {UPDATED[-4:]} {PRODUCT_NAME}</div>
</div></footer>
</body></html>"""


def _page(title: str, body: str) -> str:
    return layout(title, f"""<h1>{escape(title)}</h1>
<p class="updated">{BOT_NAME} ({PRODUCT_NAME}) · Last updated {UPDATED}</p>
{body}""")


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
