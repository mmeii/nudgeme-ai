import logging
from typing import Optional

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from .config import Settings

logger = logging.getLogger(__name__)


class SmsService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def send_message(self, body: str, to_number: Optional[str] = None) -> None:
        to = to_number or self.settings.user_phone_number
        try:
            message = self.client.messages.create(body=body, from_=self.settings.twilio_from_number, to=to)
        except TwilioRestException as exc:
            logger.exception("Failed to send SMS: %s", exc)
            raise
        logger.info("Sent SMS %s to %s", message.sid, to)
