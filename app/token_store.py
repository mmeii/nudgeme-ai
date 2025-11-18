import json
from pathlib import Path
from typing import Any, Dict, Optional

from google.oauth2.credentials import Credentials


class TokenStore:
    """Persist Google OAuth tokens locally in a JSON file."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, token_data: Dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(token_data, handle, indent=2)

    def load_credentials(self, client_id: str, client_secret: str) -> Optional[Credentials]:
        data = self.load()
        if not data:
            return None
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=client_id,
            client_secret=client_secret,
            scopes=data.get("scopes", ["https://www.googleapis.com/auth/calendar"]),
        )
        return creds

    def save_credentials(self, creds: Credentials) -> None:
        payload = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "scopes": creds.scopes,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
        self.save(payload)
