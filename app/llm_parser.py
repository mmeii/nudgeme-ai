import json
import logging
from typing import Any, Dict

from .config import Settings
from .models import IntentResult

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - openai optional
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Nudgeme, a text concierge for Google Calendar via SMS.
Personality: {personality}
Read the user's message and respond ONLY with JSON that matches this schema:
{
  "intent": "create_event | reschedule_event | cancel_event | list_events",
  "payload": {
     # describe the fields needed for that intent.
     # timestamps MUST be RFC3339 strings.
  },
  "confidence": 0.0-1.0
}
If you are unsure, set intent to "unknown" and confidence <= 0.3.
"""


class LLMParser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        self.system_prompt = SYSTEM_PROMPT.format(personality=settings.personality_prompt)
        if settings.openai_api_key and OpenAI:
            self._client = OpenAI(api_key=settings.openai_api_key)

    def parse_intent(self, text: str) -> IntentResult:
        text = text.strip()
        if not text:
            return IntentResult(intent="unknown", payload={}, original_text=text, confidence=0.0)

        if self._client:
            try:
                response = self._client.responses.create(
                    model="gpt-4o-mini",
                    input=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": text},
                    ],
                )
                content = response.output[0].content[0].text  # type: ignore[attr-defined]
                parsed: Dict[str, Any] = json.loads(content)
                intent = parsed.get("intent", "unknown")
                payload = parsed.get("payload", {})
                confidence = float(parsed.get("confidence", 0.5))
                logger.debug("LLM intent parsed: %s", parsed)
                return IntentResult(
                    intent=intent if intent in IntentResult.model_fields["intent"].annotation.__args__ else "unknown",  # type: ignore[attr-defined]
                    payload=payload,
                    original_text=text,
                    confidence=confidence,
                    raw_response=parsed,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("LLM parsing failed, falling back to heuristics: %s", exc)

        return self._fallback_intent(text)

    def _fallback_intent(self, text: str) -> IntentResult:
        lowered = text.lower()
        payload: Dict[str, Any] = {"text": text}
        intent = "unknown"
        confidence = 0.35

        if any(keyword in lowered for keyword in ["add", "create", "schedule"]):
            intent = "create_event"
        elif any(keyword in lowered for keyword in ["move", "reschedule", "delay", "shift"]):
            intent = "reschedule_event"
        elif any(keyword in lowered for keyword in ["cancel", "delete", "remove"]):
            intent = "cancel_event"
        elif "what" in lowered and "schedule" in lowered or "list" in lowered:
            intent = "list_events"

        if intent == "unknown":
            confidence = 0.1
        else:
            confidence = 0.5

        logger.debug("Heuristic intent=%s text=%s", intent, text)
        return IntentResult(intent=intent, payload=payload, original_text=text, confidence=confidence)
