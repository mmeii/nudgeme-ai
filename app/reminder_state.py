import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple


@dataclass
class ReminderKey:
    event_id: str
    reminder_type: str

    def to_tuple(self) -> Tuple[str, str]:
        return self.event_id, self.reminder_type


class ReminderStateStore:
    """Track which reminders have already been sent to avoid duplicates."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, Dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._state = {}
            return
        with self.path.open("r", encoding="utf-8") as handle:
            self._state = json.load(handle)

    def _persist(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self._state, handle, indent=2)

    def has_sent(self, event_id: str, reminder_type: str, last_updated: str) -> bool:
        event_state = self._state.get(event_id)
        if not event_state:
            return False
        if event_state.get("last_updated") != last_updated:
            return False
        return reminder_type in event_state.get("sent", [])

    def mark_sent(self, event_id: str, reminder_type: str, last_updated: str) -> None:
        event_state = self._state.setdefault(event_id, {"sent": [], "last_updated": last_updated})
        if event_state.get("last_updated") != last_updated:
            event_state["sent"] = []
            event_state["last_updated"] = last_updated
        if reminder_type not in event_state["sent"]:
            event_state["sent"].append(reminder_type)
            event_state["sent"].sort()
        self._persist()

    def clear_event(self, event_id: str) -> None:
        if event_id in self._state:
            self._state.pop(event_id)
            self._persist()
