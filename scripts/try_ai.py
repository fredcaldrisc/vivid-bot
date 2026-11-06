"""Live check of VIVID's Claude parsing on English and Twi samples.

Needs ANTHROPIC_API_KEY in .env. Makes about 8 small Claude calls.
Run:  venv\\Scripts\\python scripts\\try_ai.py
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vivid.ai import ReminderAI  # noqa: E402  (loads .env via vivid.config below)
from vivid.config import Settings  # noqa: E402

CASUAL = [
    "Remind me to call mom at 6:30 pm",
    "remind me tmrw 7am to take my drugs",
    "Kae me sɛ mɛfrɛ maame anwummerɛ nnɔnsia",
    "6:30pm",
    "Hello, how are you?",
]
VIVID = [
    ("call mom", "remind me to call mom at 6:30pm to ask her if she has taken her medication"),
    ("frɛ maame", "Kae me sɛ mɛfrɛ maame abisa no sɛ wanom n'aduro anaa"),
]


def main() -> None:
    settings = Settings()
    ai = ReminderAI(settings.anthropic_model)
    now = datetime.now(ZoneInfo(settings.timezone))
    print(f"Now: {now:%a %Y-%m-%d %H:%M} ({settings.timezone})\n")
    for text in CASUAL:
        r = ai.understand(text, now)
        print(f"{text!r}\n  -> reminder={r.is_reminder} task={r.task!r} due={r.due_local!r} lang={r.language}\n")
    for task, text in VIVID:
        print(f"{text!r}\n  -> {ai.rewrite(text, task)}\n")


if __name__ == "__main__":
    main()
