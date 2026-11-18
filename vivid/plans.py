"""Vivid Reminders subscription plans.

Standard: WhatsApp reminders that repeat until you tap Done (default GHS 30 for 20 days).
Premium:  everything in Standard for longer (default GHS 70 for 30 days), plus SMS backup
          (up to 3 per reminder) when WhatsApp can't reach your phone.

Prices are in pesewas (3000 = GHS 30) and come from settings, so they can be
changed on Render without touching code.
"""

from dataclasses import dataclass

STANDARD = "standard"
PREMIUM = "premium"


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_pesewas: int
    days: int
    sms_backups: int  # SMS sent per reminder when WhatsApp can't reach the phone

    @property
    def price_text(self) -> str:
        cedis = self.price_pesewas / 100
        return f"GHS {cedis:.0f}" if self.price_pesewas % 100 == 0 else f"GHS {cedis:.2f}"

    @property
    def features(self) -> list[str]:
        items = [
            "Unlimited reminders on WhatsApp",
            "English or Twi, text or voice notes",
            "Keeps reminding you until you tap Done",
            "Done / Missed / Upcoming history",
        ]
        if self.sms_backups:
            times = "once" if self.sms_backups == 1 else f"up to {self.sms_backups} times"
            items.insert(3, f"SMS backup {times} per reminder when WhatsApp can't reach you")
        return items


def build_plans(standard_pesewas: int, premium_pesewas: int, standard_days: int, premium_days: int,
                premium_sms: int) -> dict[str, Plan]:
    return {
        STANDARD: Plan(STANDARD, "Standard", standard_pesewas, standard_days, 0),
        PREMIUM: Plan(PREMIUM, "Premium", premium_pesewas, premium_days, premium_sms),
    }


def parse_choice(text: str) -> str | None:
    """Understands a subscriber picking a plan: '1', 'standard', '2', 'premium', 'upgrade'."""
    words = " ".join(text.lower().split())
    if words in {"1", "standard", "plan 1", "standard plan", "basic"}:
        return STANDARD
    if words in {"2", "premium", "plan 2", "premium plan", "upgrade", "pro"}:
        return PREMIUM
    return None
