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

# VIVID's WhatsApp number (+233 50 628 1109), used unless WHATSAPP_PUBLIC_NUMBER overrides it.
DEFAULT_PUBLIC_NUMBER = "233506281109"


def whatsapp_number() -> str:
    raw = os.environ.get("WHATSAPP_PUBLIC_NUMBER", "") or DEFAULT_PUBLIC_NUMBER
    return "".join(ch for ch in raw if ch.isdigit())


def whatsapp_link(text: str = "Hi VIVID") -> str:
    return f"https://wa.me/{whatsapp_number()}?text={quote(text)}"


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
    ("👉 Nudges until Done", "VIVID keeps nudging you on WhatsApp until you tap Done, so nothing slips."),
    ("✅ Done, Missed, Upcoming", "Tap Done when it's done. Send “list” to see what's coming up, done and missed."),
]
SMS_FEATURE = ("📶 SMS backup (Premium)", "If WhatsApp can't reach your phone, VIVID texts you the reminder, up to 3 times.")


def _plans_summary(plans: dict, premium_enabled: bool) -> str:
    std, pre = plans["standard"], plans["premium"]
    if not premium_enabled:
        return f"<b>{std.name}</b>: {std.price_text} for {std.days} days. <b>{pre.name}</b> is coming soon"
    return (f"<b>{std.name}</b> {std.price_text} for {std.days} days, or <b>{pre.name}</b> "
            f"{pre.price_text} for {pre.days} days with SMS backup")


def home_page(plans: dict, premium_enabled: bool = True) -> str:
    hero = f"""<section class="hero"><div class="wrap">
  <img src="/logo-256.png" alt="{BOT_NAME} logo" width="160" height="160">
  <h1>Never forget <span class="grad">what matters</span>.</h1>
  <p>{BOT_NAME} reminds you on WhatsApp at exactly the right time, in English or Twi, by text or voice note.</p>
  {_wa_button()}<a class="btn btn-ghost" href="/how-it-works">How it works</a>
</div></section>"""
    features = FEATURES[:5] + ([SMS_FEATURE] if premium_enabled else []) + FEATURES[5:]
    cards = "\n".join(f'<li class="card"><h3>{t}</h3><p>{d}</p></li>' for t, d in features)
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
<p>{_plans_summary(plans, premium_enabled)}. Pay with mobile money or card. <a href="/pricing">See pricing</a>.</p>
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
      (with your voice note, if you recorded one) and keeps <b>nudging</b> you until you tap <b>✅ Done</b>.
      On Premium, if your phone is offline, it texts you by SMS (up to 3 times).
      Reminders you never mark become <b>Missed</b>.</li>
</ol>

<h2>Handy commands</h2>
<ul class="cards">
  <li class="card"><h3>list</h3><p>See your Upcoming, Done and Missed reminders.</p></li>
  <li class="card"><h3>done</h3><p>Mark the reminder you just got as done.</p></li>
  <li class="card"><h3>cancel 3</h3><p>Cancel upcoming reminder number 3.</p></li>
  <li class="card"><h3>status</h3><p>Check your plan and when it renews.</p></li>
  <li class="card"><h3>premium</h3><p>Upgrade to Premium for SMS backup.</p></li>
  <li class="card"><h3>help</h3><p>Show the menu again.</p></li>
  <li class="card"><h3>delete my data</h3><p>Erase everything {BOT_NAME} holds about you.</p></li>
</ul>
{_cta()}"""
    return layout("How it works", main)


def _plan_card(plan, number: int) -> str:
    items = "\n".join(f"    <li>{escape(f)}</li>" for f in plan.features)
    return f"""<div class="price">
  <p class="muted">{PRODUCT_NAME} {escape(plan.name)}</p>
  <p class="amount">{plan.price_text}</p>
  <p class="muted">for {plan.days} days</p>
  <ul>
{items}
  </ul><br>
  {_wa_button(f"Get {plan.name} on WhatsApp")}
  <p class="muted">Then reply <b>{number}</b> to {BOT_NAME}.</p>
</div>"""


def pricing_page(plans: dict, premium_enabled: bool = True) -> str:
    std, pre = plans["standard"], plans["premium"]
    if not premium_enabled:
        main = f"""<h1>Pricing</h1>
<p class="muted">One simple plan. No app, no contract.</p>
<div class="cards">
{_plan_card(std, 1)}
<div class="price">
  <p class="muted">{PRODUCT_NAME} {escape(pre.name)}</p>
  <p class="amount">Coming soon</p>
  <p class="muted">More days, SMS backup when WhatsApp can't reach you, and team plans.</p>
</div>
</div>
<h2>How do I pay?</h2>
<p>Message {BOT_NAME} on WhatsApp and reply <b>1</b>. {BOT_NAME} sends you a secure Paystack link where you pay
with mobile money or card, and confirms on WhatsApp as soon as the payment goes through.</p>
<h2>Can I stop?</h2>
<p>Yes. Your plan simply ends after {std.days} days unless you pay again. You can also
<a href="/data-deletion">delete all your data</a> at any time.</p>"""
        return layout("Pricing", main)
    main = f"""<h1>Pricing</h1>
<p class="muted">Two simple plans. No app, no contract.</p>
<div class="cards">
{_plan_card(std, 1)}
{_plan_card(pre, 2)}
</div>
<h2>How do I pay?</h2>
<p>Message {BOT_NAME} on WhatsApp and reply <b>1</b> for {std.name} or <b>2</b> for {pre.name}. {BOT_NAME}
sends you a secure Paystack link where you pay with mobile money or card, and confirms on WhatsApp as soon as
the payment goes through. Already on {std.name}? Send <b>premium</b> to upgrade.</p>
<h2>Can I stop?</h2>
<p>Yes. Your plan simply ends after its {std.days} days ({std.name}) or {pre.days} days ({pre.name})
unless you pay again. You can also
<a href="/data-deletion">delete all your data</a> at any time.</p>"""
    return layout("Pricing", main)
