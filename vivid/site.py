"""The public website: home, how it works and pricing.

The "Message VIVID on WhatsApp" button opens a chat with the number in WHATSAPP_PUBLIC_NUMBER
(international format, digits only, e.g. 233201234567). Change that one setting on Render when
VIVID moves to its Ghanaian number; nothing else needs editing.
"""

import os
from html import escape
from urllib.parse import quote

from . import BOT_NAME, PRODUCT_NAME
from .pages import layout

# Meta's test number, used until WHATSAPP_PUBLIC_NUMBER is set.
DEFAULT_PUBLIC_NUMBER = "15552049961"


def whatsapp_number() -> str:
    raw = os.environ.get("WHATSAPP_PUBLIC_NUMBER", "") or DEFAULT_PUBLIC_NUMBER
    return "".join(ch for ch in raw if ch.isdigit())


def whatsapp_link(text: str = "Hi VIVID") -> str:
    return f"https://wa.me/{whatsapp_number()}?text={quote(text)}"


def price_text(price_pesewas: int) -> str:
    """2000 -> 'GHS 20', 2550 -> 'GHS 25.50'."""
    cedis = price_pesewas / 100
    return f"GHS {cedis:.0f}" if price_pesewas % 100 == 0 else f"GHS {cedis:.2f}"


def _wa_button(label: str = f"Message {BOT_NAME} on WhatsApp") -> str:
    return f'<a class="btn btn-wa" href="{escape(whatsapp_link())}" rel="noopener">{escape(label)}</a>'


def _cta() -> str:
    return f"""<div class="cta">
<p><b>Ready?</b> Say hi to {BOT_NAME} and send your first reminder.</p>
{_wa_button()}
</div>"""


FEATURES = [
    ("💬 Just WhatsApp", "No app to install. Chat with VIVID like you chat with a friend."),
    ("🇬🇭 English or Twi", "Write or speak in the language you're comfortable with."),
    ("🎙️ Text or voice notes", "Type your reminder, or record a voice note. VIVID plays your own voice back to you."),
    ("✨ Vivid descriptions", "Add the details that matter (who, where, why) so the reminder tells you exactly what to do."),
    ("📶 SMS backup", "If WhatsApp can't reach your phone in time, VIVID sends the reminder by SMS."),
    ("✅ Done, Missed, Upcoming", "Tap Done when it's done. Send “list” to see what's coming up, done and missed."),
]


def home_page(price_pesewas: int, days: int) -> str:
    hero = f"""<section class="hero"><div class="wrap">
  <img src="/logo-256.png" alt="{BOT_NAME} logo" width="160" height="160">
  <h1>Never forget <span class="grad">what matters</span>.</h1>
  <p>{BOT_NAME} reminds you on WhatsApp at exactly the right time, in English or Twi, by text or voice note.</p>
  {_wa_button()}<a class="btn btn-ghost" href="/how-it-works">How it works</a>
</div></section>"""
    cards = "\n".join(f'<li class="card"><h3>{t}</h3><p>{d}</p></li>' for t, d in FEATURES)
    main = f"""<h2>What {BOT_NAME} does</h2>
<ul class="cards">
{cards}
</ul>

<h2>Looks like this</h2>
<div class="chat" aria-label="Example WhatsApp conversation">
  <div class="you">Remind me to call mom at 6:30pm</div>
  <div class="bot">Got it ✅ Tell me the vivid description: what exactly should I remind you?</div>
  <div class="you">Ask her if she has taken her medication</div>
  <div class="bot">⏰ 6:30pm: Call Mom and ask her if she has taken her medication. Tap ✅ Done when you've done it.</div>
</div>

<h2>Simple pricing</h2>
<p><b>{price_text(price_pesewas)}</b> for {days} days of {PRODUCT_NAME}. Pay with mobile money or card.
<a href="/pricing">See pricing</a>.</p>
{_cta()}"""
    return layout(f"{PRODUCT_NAME} on WhatsApp", main, hero)


def how_it_works_page() -> str:
    main = f"""<h1>How it works</h1>
<p class="muted">Four steps, all inside WhatsApp.</p>
<ol class="steps">
  <li><b>Say hi.</b> Open WhatsApp and message {BOT_NAME}. New here? {BOT_NAME} sends you a link to subscribe
      with mobile money or card.</li>
  <li><b>Tell {BOT_NAME} what, when and who.</b> Type it or send a voice note, in English or Twi.<br>
      <i>“Remind me to call driver Kwame on Friday 1pm.”</i></li>
  <li><b>Add the vivid description.</b> {BOT_NAME} asks for the details: what exactly to say, bring or do.
      You can answer by text or voice note.</li>
  <li><b>Get reminded, then tap Done.</b> At the right time {BOT_NAME} sends your reminder on WhatsApp
      (with your voice note, if you recorded one). If your phone is offline, it sends an SMS instead.
      Tap <b>✅ Done</b> when it's done; reminders you don't mark become <b>Missed</b>.</li>
</ol>

<h2>Handy commands</h2>
<ul class="cards">
  <li class="card"><h3>list</h3><p>See your Upcoming, Done and Missed reminders.</p></li>
  <li class="card"><h3>done</h3><p>Mark the reminder you just got as done.</p></li>
  <li class="card"><h3>cancel 3</h3><p>Cancel upcoming reminder number 3.</p></li>
  <li class="card"><h3>status</h3><p>Check your subscription.</p></li>
  <li class="card"><h3>help</h3><p>Show the menu again.</p></li>
  <li class="card"><h3>delete my data</h3><p>Erase everything {BOT_NAME} holds about you.</p></li>
</ul>
{_cta()}"""
    return layout("How it works", main)


def pricing_page(price_pesewas: int, days: int) -> str:
    main = f"""<h1>Pricing</h1>
<p class="muted">One simple plan. No app, no contract.</p>
<div class="price">
  <p class="muted">{PRODUCT_NAME}</p>
  <p class="amount">{price_text(price_pesewas)}</p>
  <p class="muted">for {days} days</p>
  <ul>
    <li>Unlimited reminders on WhatsApp</li>
    <li>English or Twi, text or voice notes</li>
    <li>SMS backup when WhatsApp can't reach you</li>
    <li>Done / Missed / Upcoming history</li>
  </ul><br>
  {_wa_button("Subscribe on WhatsApp")}
</div>
<h2>How do I pay?</h2>
<p>Message {BOT_NAME} on WhatsApp. It sends you a secure Paystack link where you pay with mobile money
or card. {BOT_NAME} confirms on WhatsApp as soon as the payment goes through.</p>
<h2>Can I stop?</h2>
<p>Yes. Your subscription simply ends after {days} days unless you pay again. You can also
<a href="/data-deletion">delete all your data</a> at any time.</p>"""
    return layout("Pricing", main)
