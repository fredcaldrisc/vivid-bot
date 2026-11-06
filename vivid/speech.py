"""Speech-to-text for voice notes.

Claude cannot listen to audio, so voice notes are transcribed first, only to
find the task and the time. The original recording is what gets played back.

Default provider: GhanaNLP Khaya ASR (supports Twi and English). Set ASR_URL to
the transcription endpoint from your GhanaNLP developer portal, e.g.
    https://translation-api.ghananlp.org/asr/v1/transcribe?language={lang}
and ASR_KEY to your subscription key. Check the exact URL and accepted audio
formats in the portal: WhatsApp voice notes are OGG/Opus.

If ASR is not configured or fails, the bot simply asks the user to type the time.
"""

import logging

import requests

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, url: str = "", key: str = "", timeout: float = 60.0):
        self.url = url
        self.key = key
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def transcribe(self, audio: bytes, mime: str, lang: str = "tw") -> str | None:
        if not self.enabled:
            return None
        try:
            resp = requests.post(
                self.url.format(lang=lang),
                data=audio,
                headers={"Ocp-Apim-Subscription-Key": self.key, "Content-Type": mime.split(";")[0]},
                timeout=self.timeout,
            )
            if resp.status_code >= 400:
                log.warning("ASR failed (%s): %s", resp.status_code, resp.text[:300])
                return None
            try:
                body = resp.json()
            except ValueError:
                return resp.text.strip() or None
            if isinstance(body, str):
                return body.strip() or None
            if isinstance(body, dict):
                for key in ("text", "transcription", "transcript", "result"):
                    if isinstance(body.get(key), str):
                        return body[key].strip() or None
            log.warning("Unrecognised ASR response: %r", body)
        except requests.RequestException:
            log.exception("ASR request failed")
        return None
