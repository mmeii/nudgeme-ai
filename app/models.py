from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class EventCreateRequest(BaseModel):
    summary: str = Field(description="Human friendly title")
    start_time: datetime = Field(description="ISO datetime of start (timezone-aware)")
    end_time: datetime = Field(description="ISO datetime of end (timezone-aware)")
    description: Optional[str] = None
    timezone: Optional[str] = Field(default=None, description="Override timezone for start/end")


class EventUpdateRequest(BaseModel):
    summary: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None


class EventResponse(BaseModel):
    id: str
    summary: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    timezone: str
    status: str
    updated_at: Optional[datetime] = None
    etag: Optional[str] = None


class IntentResult(BaseModel):
    intent: Literal["create_event", "reschedule_event", "cancel_event", "list_events", "unknown"]
    payload: Dict[str, Any] = Field(default_factory=dict)
    original_text: str
    confidence: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None


class TwilioWebhookResponse(BaseModel):
    message: str
    success: bool = True
