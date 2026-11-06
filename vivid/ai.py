"""Claude does the language work: reading casual reminders (English or Twi)
and rewriting the vivid description into a reporting-style reminder."""

import logging
from datetime import datetime

import anthropic
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

UNDERSTAND_SYSTEM = """You are the language engine of VIVID, a WhatsApp reminder assistant used in Ghana.
Users write in English, Twi (Akan), or a mix of both, often casually and with typos.

Read the user's message and extract:
- is_reminder: true if the message asks to be reminded of something, or only states a time
  (the user may be answering "what time?"). false for greetings, questions, or anything else.
- task: the action to be reminded of, short, in the user's language, without the time, keeping
  who it involves (e.g. "call mom", "call driver Kwame", "frɛ maame"). Empty string if none.
- who: the person the task involves other than the user, with any role they were given
  (e.g. "driver Kwame", "mom"). Empty string if nobody else is involved.
- due_local: the date and time the reminder should fire, as "YYYY-MM-DDTHH:MM" in the user's local
  time, resolved against the current local time you are given. If only a time is given and it has
  already passed today, use tomorrow. Understand Twi time expressions (e.g. "anɔpa" morning,
  "awia" afternoon, "anwummerɛ" evening, "anadwo" night, "ɔkyena" tomorrow, "nnɛ" today,
  "nnɔnsia" six o'clock). Empty string if no time can be determined.
- language: "tw" if the user mainly wrote Twi, otherwise "en"."""

REWRITE_SYSTEM = """You are VIVID, a WhatsApp reminder assistant. A user has saved a detailed ("vivid")
description of something they want to be reminded about. Rewrite it as the reminder message
VIVID will send them at the moment it is due, in reporting form, addressed to the user.

Rules:
- Start with "Time to" (or the natural Twi equivalent, e.g. "Bere aso sɛ", if the description is in Twi).
- Keep every detail the user gave (who, what, why). Drop the time itself and phrases like "remind me".
- One or two sentences, plain text, no emojis, no quotation marks.

Examples:
"remind me to call mom at 6:30pm to ask her if she has taken her medication"
-> Time to call mom to ask her if she has taken her medication.
"Remind me to call driver Kwame to tell him to go and service the truck on Friday 1pm after his trip"
-> Time to call driver Kwame to ask him to go and service the truck after his trip."""


class Understanding(BaseModel):
    is_reminder: bool
    task: str = Field(description="Action to be reminded of, without the time")
    who: str = Field(description="Other person involved, e.g. 'driver Kwame', or empty")
    due_local: str = Field(description='"YYYY-MM-DDTHH:MM" local time, or empty string')
    language: str = Field(description='"en" or "tw"')


class Rewrite(BaseModel):
    message: str


class AIError(RuntimeError):
    pass


class ReminderAI:
    def __init__(self, model: str = "claude-opus-5-5", client: anthropic.Anthropic | None = None):
        self.model = model
        self.client = client or anthropic.Anthropic()

    def _parse(self, system: str, user_content: str, schema: type[BaseModel]):
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=2000,
                system=system,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": user_content}],
                output_format=schema,
            )
        except anthropic.APIConnectionError as exc:
            raise AIError("Could not reach Claude") from exc
        except anthropic.RateLimitError as exc:
            raise AIError("Claude rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise AIError(f"Claude returned no usable output (stop_reason={response.stop_reason})")
        return response.parsed_output

    def understand(self, text: str, now_local: datetime) -> Understanding:
        content = (
            f"Current local time: {now_local.strftime('%A %Y-%m-%d %H:%M')} ({now_local.tzinfo})\n\n"
            f"User message:\n{text}"
        )
        return self._parse(UNDERSTAND_SYSTEM, content, Understanding)

    def rewrite(self, vivid_description: str, task: str) -> str:
        content = f"Task: {task}\nVivid description from the user:\n{vivid_description}"
        return self._parse(REWRITE_SYSTEM, content, Rewrite).message.strip()
