from __future__ import annotations

import secrets
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from google_auth_oauthlib.flow import Flow

from .calendar_service import GoogleCalendarClient
from .config import Settings, get_settings
from .token_store import TokenStore

router = APIRouter(prefix="/oauth/google", tags=["oauth"])

_state_cache: Dict[str, str] = {}


def _build_flow(settings: Settings, state: str | None = None) -> Flow:
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=GoogleCalendarClient.SCOPES, state=state)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


@router.get("/start")
def start_oauth(settings: Settings = Depends(get_settings)) -> Dict[str, str]:
    state = secrets.token_urlsafe(16)
    flow = _build_flow(settings, state=state)
    authorization_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _state_cache[state] = returned_state
    return {"authorization_url": authorization_url, "state": returned_state}


@router.get("/callback")
def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    settings: Settings = Depends(get_settings),
) -> Dict[str, str]:
    cached = _state_cache.pop(state, None)
    if not cached:
        raise HTTPException(status_code=400, detail="Unknown or expired state parameter")
    flow = _build_flow(settings, state=state)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    token_store = TokenStore(settings.google_token_path)
    token_store.save_credentials(credentials)
    return {"status": "ok", "message": "Google account connected"}
