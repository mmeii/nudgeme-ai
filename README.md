# Nudgeme AI

A playful SMS-first assistant that keeps your Google Calendar on track. Nudgeme connects Google Calendar, Twilio SMS, and an optional LLM so you can manage your schedule by texting natural language commands.

## Features (MVP)
- **Google Calendar bridge** – OAuth sign-in, refresh-token persistence, list/create/update/delete events.
- **SMS concierge** – Twilio webhook for inbound messages + outbound reminders/confirmations.
- **Natural-language intents** – Optional OpenAI parsing with a heuristic fallback that covers common phrases.
- **Reminder engine** – APScheduler job sends reminders 2h and 10m before every event, with duplicate-prevention.
- **FastAPI backend** – REST endpoints for event CRUD + Google OAuth callback + Twilio webhook.
- **Logging & resilience** – Structured logging for SMS + calendar ops, retry-friendly error handling.
- **Configurable personality** – Emoji-friendly tone powered by an env-configurable prompt.

## Project structure
```
app/
├── calendar_service.py   # Google Calendar wrapper
├── config.py             # Pydantic settings loader
├── llm_parser.py         # Intent detection via OpenAI or heuristics
├── main.py               # FastAPI app + API routes + Twilio webhook
├── models.py             # Pydantic models for events/intents
├── oauth.py              # Google OAuth endpoints
├── reminder_engine.py    # Background reminder scheduler
├── reminder_state.py     # Duplicate reminder tracking
├── sms_service.py        # Twilio send helper
└── token_store.py        # Local JSON persistence for OAuth tokens
scripts/
└── setup.sh              # Bootstrap venv, install deps, copy .env
```

## Prerequisites
- Python 3.11+
- A Google Cloud project with Calendar API enabled
- A Twilio account & SMS-capable number
- (Optional) OpenAI API key for better intent parsing
- `ngrok` (or similar) to expose the local Twilio webhook

## Quick start
1. Clone the repo and run the setup script:
   ```bash
   ./scripts/setup.sh
   ```
   This creates `.venv`, installs dependencies, and copies `.env.example` to `.env`.
2. Fill out `.env` with your Google, Twilio, and (optional) OpenAI credentials.
3. Activate the virtualenv and start FastAPI:
   ```bash
   source .venv/bin/activate
   uvicorn app.main:app --reload
   ```
4. Complete Google OAuth:
   - Visit `http://localhost:8000/oauth/google/start` to grab the auth URL.
   - Open the URL in a browser, approve access, and let it redirect to the callback.
   - The callback persists the refresh token at `data/google_token.json`.
5. Point Twilio to your webhook:
   - Run `ngrok http 8000` (or similar) and copy the HTTPS URL.
   - In Twilio’s console, set the Messaging webhook to `https://<ngrok-id>.ngrok.io/twilio/webhook`.
6. Text your Twilio number with commands like “What’s on my schedule?” or “Move my dentist appointment to 3pm.”

## API reference
| Endpoint | Method | Description |
| --- | --- | --- |
| `/twilio/webhook` | POST | Twilio inbound SMS (responds with TwiML). |
| `/oauth/google/start` | GET | Returns the Google OAuth consent URL + state. |
| `/oauth/google/callback` | GET | Exchanges auth code, stores refresh token. |
| `/events/today` | GET | List today’s events from Google Calendar. |
| `/events` | POST | Create an event (expects `EventCreateRequest`). |
| `/events/{id}` | PATCH | Modify summary/time/description. |
| `/events/{id}` | DELETE | Cancel an event. |

### Event payloads
```jsonc
// POST /events
{
  "summary": "Lunch with Jamie",
  "start_time": "2024-07-01T12:00:00-07:00",
  "end_time": "2024-07-01T13:00:00-07:00",
  "description": "Catch-up at Tartine",
  "timezone": "America/Los_Angeles"
}

// PATCH /events/{id}
{
  "start_time": "2024-07-01T15:00:00-07:00",
  "end_time": "2024-07-01T16:00:00-07:00"
}
```

## Reminder engine
- Runs every minute via APScheduler.
- Looks 24h ahead and schedules reminders 2h and 10m before each event.
- Tracks sent reminders in `data/reminder_state.json` (etag/updated timestamp aware) to prevent duplicates and handle moved events.
- Uses the fun personality defined in `PERSONALITY_PROMPT` when crafting SMS content.

## Logging & troubleshooting
- Logs stream to stdout by default (configure via `LOGLEVEL` env or edit `logging.basicConfig`).
- All inbound/outbound SMS, LLM outputs, and calendar mutations are logged.
- Google Calendar exceptions bubble up as HTTP 502 responses; Twilio webhook always returns a friendly text.

## Deployment notes
- Use something like Railway/Fly/Render for an always-on FastAPI app.
- Swap `uvicorn --reload` with `uvicorn app.main:app --host 0.0.0.0 --port 8000` for production.
- Store `.env` and token JSON files securely.
- If you need multi-user support, replace the JSON token store with SQLite keyed by phone number.

## Next steps
- Plug in a storage layer for multi-user tokens + reminder history.
- Add richer LLM parsing (entities, free-form text confirmations).
- Build a lightweight frontend for OAuth onboarding + analytics.
