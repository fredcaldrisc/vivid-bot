"""Background loop that sends reminders when they fall due."""

import logging
import threading

log = logging.getLogger(__name__)


def start_scheduler(bot, interval_seconds: int = 20) -> threading.Event:
    """Starts a daemon thread; set the returned event to stop it."""
    stop = threading.Event()

    def loop():
        log.info("VIVID scheduler running every %ss", interval_seconds)
        while not stop.is_set():
            try:
                sent = bot.tick()
                if sent:
                    log.info("Fired %s reminder(s)", sent)
            except Exception:
                log.exception("Scheduler tick failed")
            stop.wait(interval_seconds)

    threading.Thread(target=loop, name="vivid-scheduler", daemon=True).start()
    return stop
