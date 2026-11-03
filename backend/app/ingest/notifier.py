"""Sends events to the API (owner: Student A, task A2).

POST API_INTERNAL_URL/api/internal/events with an Event from the contract.
Student B's hub forwards them to the dashboard and the phone.
The worker must keep running when the API is down, so post() never raises:
it logs once when the API becomes unreachable and once when it is back.
"""

import logging
from datetime import UTC, datetime

import httpx

from app.contracts import Event, EventType

log = logging.getLogger(__name__)


class EventNotifier:
    def __init__(self, api_url: str, timeout_s: float = 2.0) -> None:
        self._client = httpx.Client(base_url=api_url, timeout=timeout_s)
        self._api_down = False

    def post(self, event_type: EventType, data: dict) -> bool:
        """Send one event; True if the API accepted it."""
        event = Event(type=event_type, ts=datetime.now(UTC), data=data)
        try:
            response = self._client.post("/api/internal/events", json=event.model_dump(mode="json"))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if not self._api_down:
                log.warning("API not reachable (%s); events are dropped until it is back", exc)
                self._api_down = True
            return False
        if self._api_down:
            log.info("API reachable again")
            self._api_down = False
        return True

    def close(self) -> None:
        self._client.close()
