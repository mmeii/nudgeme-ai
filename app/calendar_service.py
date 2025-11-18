from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import Settings
from .models import EventCreateRequest, EventResponse, EventUpdateRequest
from .token_store import TokenStore

logger = logging.getLogger(__name__)


class CalendarError(Exception):
    pass


class MissingCredentialsError(CalendarError):
    pass


class GoogleCalendarClient:
    """Wrapper around the Google Calendar API."""

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, settings: Settings, token_store: TokenStore):
        self.settings = settings
        self.token_store = token_store
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        creds = self.token_store.load_credentials(
            client_id=self.settings.google_client_id, client_secret=self.settings.google_client_secret
        )
        if not creds:
            raise MissingCredentialsError("Google OAuth token not found. Complete the OAuth flow first.")
        if creds.expired and creds.refresh_token:
            logger.info("Refreshing Google OAuth token")
            creds.refresh(Request())
            self.token_store.save_credentials(creds)
        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def _normalize_event(self, event: dict) -> EventResponse:
        start = event.get("start", {})
        end = event.get("end", {})
        timezone_name = start.get("timeZone") or self.settings.timezone
        start_dt = self._parse_rfc3339(start.get("dateTime"))
        end_dt = self._parse_rfc3339(end.get("dateTime"))
        updated = event.get("updated") or event.get("created")
        updated_dt = self._parse_rfc3339(updated) if updated else None
        return EventResponse(
            id=event.get("id"),
            summary=event.get("summary", "(no title)"),
            description=event.get("description"),
            start_time=start_dt,
            end_time=end_dt,
            timezone=timezone_name,
            status=event.get("status", "confirmed"),
            updated_at=updated_dt,
            etag=event.get("etag"),
        )

    @staticmethod
    def _parse_rfc3339(value: Optional[str]) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def list_events(self, time_min: datetime, time_max: datetime, max_results: int = 20) -> List[EventResponse]:
        service = self._get_service()
        try:
            result = (
                service.events()
                .list(
                    calendarId=self.settings.google_calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=max_results,
                )
                .execute()
            )
        except HttpError as exc:
            logger.exception("Failed to list events: %s", exc)
            raise CalendarError(str(exc)) from exc
        items = result.get("items", [])
        return [self._normalize_event(item) for item in items]

    def list_events_today(self) -> List[EventResponse]:
        tz = ZoneInfo(self.settings.timezone)
        now = datetime.now(tz)
        start_of_day = datetime(now.year, now.month, now.day, tzinfo=tz)
        end_of_day = start_of_day + timedelta(days=1)
        return self.list_events(start_of_day.astimezone(timezone.utc), end_of_day.astimezone(timezone.utc))

    def list_upcoming(self, hours: int = 24) -> List[EventResponse]:
        tz = ZoneInfo(self.settings.timezone)
        now = datetime.now(tz)
        later = now + timedelta(hours=hours)
        return self.list_events(now.astimezone(timezone.utc), later.astimezone(timezone.utc), max_results=50)

    def create_event(self, payload: EventCreateRequest) -> EventResponse:
        service = self._get_service()
        timezone_name = payload.timezone or self.settings.timezone
        body = {
            "summary": payload.summary,
            "description": payload.description,
            "start": {"dateTime": payload.start_time.isoformat(), "timeZone": timezone_name},
            "end": {"dateTime": payload.end_time.isoformat(), "timeZone": timezone_name},
        }
        try:
            event = service.events().insert(calendarId=self.settings.google_calendar_id, body=body).execute()
        except HttpError as exc:
            logger.exception("Failed to create event: %s", exc)
            raise CalendarError(str(exc)) from exc
        return self._normalize_event(event)

    def update_event(self, event_id: str, payload: EventUpdateRequest) -> EventResponse:
        service = self._get_service()
        body = {}
        if payload.summary is not None:
            body["summary"] = payload.summary
        if payload.description is not None:
            body["description"] = payload.description
        if payload.start_time is not None:
            body.setdefault("start", {})["dateTime"] = payload.start_time.isoformat()
            body["start"].setdefault("timeZone", self.settings.timezone)
        if payload.end_time is not None:
            body.setdefault("end", {})["dateTime"] = payload.end_time.isoformat()
            body["end"].setdefault("timeZone", self.settings.timezone)
        try:
            event = (
                service.events()
                .patch(calendarId=self.settings.google_calendar_id, eventId=event_id, body=body)
                .execute()
            )
        except HttpError as exc:
            logger.exception("Failed to update event: %s", exc)
            raise CalendarError(str(exc)) from exc
        return self._normalize_event(event)

    def delete_event(self, event_id: str) -> None:
        service = self._get_service()
        try:
            service.events().delete(calendarId=self.settings.google_calendar_id, eventId=event_id).execute()
        except HttpError as exc:
            logger.exception("Failed to delete event: %s", exc)
            raise CalendarError(str(exc)) from exc
