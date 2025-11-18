from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from twilio.twiml.messaging_response import MessagingResponse

from .calendar_service import CalendarError, GoogleCalendarClient
from .config import Settings, get_settings
from .llm_parser import LLMParser
from .models import EventCreateRequest, EventResponse, EventUpdateRequest, IntentResult
from .oauth import router as oauth_router
from .reminder_engine import ReminderEngine
from .reminder_state import ReminderStateStore
from .sms_service import SmsService
from .token_store import TokenStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("nudgeme")


class ServiceContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.token_store = TokenStore(settings.google_token_path)
        self.calendar_client = GoogleCalendarClient(settings, self.token_store)
        self.sms_service = SmsService(settings)
        self.intent_parser = LLMParser(settings)
        self.reminder_store = ReminderStateStore(settings.reminder_state_path)
        self.reminder_engine = ReminderEngine(
            calendar_client=self.calendar_client,
            sms_service=self.sms_service,
            settings=settings,
            state_store=self.reminder_store,
        )


def get_container(settings: Settings = Depends(get_settings)) -> ServiceContainer:
    global _container
    if _container is None:
        _container = ServiceContainer(settings)
    return _container


_container: ServiceContainer | None = None

app = FastAPI(title="Nudgeme AI", version="0.1.0")
app.include_router(oauth_router)


@app.on_event("startup")
async def startup_event():
    container = get_container()
    container.reminder_engine.start()


@app.on_event("shutdown")
async def shutdown_event():
    if _container:
        _container.reminder_engine.stop()


@app.get("/events/today", response_model=List[EventResponse])
def get_today_events(container: ServiceContainer = Depends(get_container)) -> List[EventResponse]:
    try:
        return container.calendar_client.list_events_today()
    except CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/events", response_model=EventResponse)
def create_event(request: EventCreateRequest, container: ServiceContainer = Depends(get_container)) -> EventResponse:
    try:
        return container.calendar_client.create_event(request)
    except CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.patch("/events/{event_id}", response_model=EventResponse)
def update_event(event_id: str, request: EventUpdateRequest, container: ServiceContainer = Depends(get_container)) -> EventResponse:
    if not request.model_dump(exclude_none=True):
        raise HTTPException(status_code=400, detail="No fields supplied")
    try:
        return container.calendar_client.update_event(event_id, request)
    except CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/events/{event_id}")
def delete_event(event_id: str, container: ServiceContainer = Depends(get_container)) -> JSONResponse:
    try:
        container.calendar_client.delete_event(event_id)
    except CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return JSONResponse({"status": "deleted", "event_id": event_id})


@app.post("/twilio/webhook")
async def twilio_webhook(request: Request, container: ServiceContainer = Depends(get_container)) -> Response:
    form = await request.form()
    from_number = form.get("From")
    inbound = form.get("Body", "").strip()
    logger.info("Incoming SMS from %s: %s", from_number, inbound)

    intent = container.intent_parser.parse_intent(inbound)
    logger.info("Parsed intent %s with confidence %.2f", intent.intent, intent.confidence)

    reply_text = handle_intent(intent, container)

    messaging_response = MessagingResponse()
    messaging_response.message(reply_text)

    logger.info("Responding via Twilio: %s", reply_text)
    return Response(content=str(messaging_response), media_type="application/xml")


def handle_intent(intent: IntentResult, container: ServiceContainer) -> str:
    try:
        if intent.intent == "list_events":
            events = container.calendar_client.list_events_today()
            if not events:
                return "📭 Nothing on the books today. Enjoy the free time!"
            lines = ["📅 Here's today:"]
            for event in events:
                lines.append(format_event_line(event))
            return "\n".join(lines)

        if intent.intent == "create_event":
            create_request = build_event_create(intent.payload)
            event = container.calendar_client.create_event(create_request)
            return f"✨ Added '{event.summary}' at {format_local_time(event.start_time)}"

        if intent.intent == "reschedule_event":
            event_id, update_request = build_event_update(intent.payload)
            event = container.calendar_client.update_event(event_id, update_request)
            return f"🔁 Rescheduled '{event.summary}' to {format_local_time(event.start_time)}"

        if intent.intent == "cancel_event":
            event_id = intent.payload.get("event_id")
            if not event_id:
                raise ValueError("Missing event_id for cancellation")
            container.calendar_client.delete_event(event_id)
            return "🗑️ Got it — event canceled."
    except CalendarError as exc:
        logger.exception("Calendar error while handling intent: %s", exc)
        return "😬 Google Calendar didn't like that. Try again in a sec?"
    except ValueError as exc:
        logger.warning("Invalid payload for %s: %s", intent.intent, exc)
        return "🤔 I need a bit more info to do that. Can you rephrase?"

    return "Sorry, I didn't understand that — mind rephrasing?"

def build_event_create(payload: dict | None) -> EventCreateRequest:
    payload = payload or {}
    for field in ("summary", "start_time", "end_time"):
        if field not in payload:
            raise ValueError(f"Missing field '{field}' for create_event")
    data = payload.copy()
    for time_field in ("start_time", "end_time"):
        if isinstance(data.get(time_field), str):
            data[time_field] = datetime.fromisoformat(data[time_field])
    return EventCreateRequest(**data)


def build_event_update(payload: dict | None) -> tuple[str, EventUpdateRequest]:
    payload = payload or {}
    if "event_id" not in payload:
        raise ValueError("Missing event_id for update")
    data = payload.copy()
    event_id = data.pop("event_id")
    if "start_time" in data and isinstance(data["start_time"], str):
        data["start_time"] = datetime.fromisoformat(data["start_time"])
    if "end_time" in data and isinstance(data["end_time"], str):
        data["end_time"] = datetime.fromisoformat(data["end_time"])
    if not data:
        raise ValueError("No update fields provided")
    return event_id, EventUpdateRequest(**data)


def format_event_line(event: EventResponse) -> str:
    start = format_local_time(event.start_time)
    end = format_local_time(event.end_time)
    return f"• {start} - {end}: {event.summary}"


def format_local_time(dt: datetime) -> str:
    local = dt.astimezone()
    return local.strftime("%I:%M %p").lstrip("0") or local.strftime("%H:%M")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
