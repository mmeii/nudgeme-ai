from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from .calendar_service import GoogleCalendarClient
from .config import Settings
from .reminder_state import ReminderStateStore
from .sms_service import SmsService

logger = logging.getLogger(__name__)


class ReminderEngine:
    """Poll upcoming events and push reminders over SMS."""

    def __init__(
        self,
        calendar_client: GoogleCalendarClient,
        sms_service: SmsService,
        settings: Settings,
        state_store: ReminderStateStore,
    ) -> None:
        self.calendar = calendar_client
        self.sms = sms_service
        self.settings = settings
        self.state_store = state_store
        self.scheduler = BackgroundScheduler(timezone=settings.timezone)
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        logger.info("Starting reminder engine")
        self.scheduler.add_job(self._tick, "interval", minutes=1, id="reminder-poll", max_instances=1)
        self.scheduler.start()
        self._running = True

    def stop(self) -> None:
        if self._running:
            logger.info("Stopping reminder engine")
            self.scheduler.shutdown(wait=False)
            self._running = False

    def _tick(self) -> None:
        try:
            events = self.calendar.list_upcoming(hours=24)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unable to fetch events for reminders: %s", exc)
            return

        now = datetime.now(ZoneInfo(self.settings.timezone))
        for event in events:
            start = event.start_time
            if start.tzinfo is None:
                start = start.replace(tzinfo=ZoneInfo(event.timezone or self.settings.timezone))
            reminders = [
                ("2h", start - timedelta(hours=2), "⏰ Heads up! '{title}' starts in ~2 hours."),
                ("10m", start - timedelta(minutes=10), "🚀 Almost go time! '{title}' kicks off in 10 minutes."),
            ]
            updated_key = (event.updated_at or event.start_time).isoformat()
            for reminder_type, trigger_at, template in reminders:
                if now >= trigger_at and not self.state_store.has_sent(event.id, reminder_type, updated_key):
                    body = template.format(title=event.summary)
                    try:
                        self.sms.send_message(body)
                        self.state_store.mark_sent(event.id, reminder_type, updated_key)
                    except Exception as exc:  # pragma: no cover
                        logger.exception("Failed to send reminder for %s: %s", event.id, exc)

        # Clean up events that are already over to keep the state file small
        horizon = now - timedelta(hours=1)
        for event in events:
            if event.end_time < horizon:
                self.state_store.clear_event(event.id)
