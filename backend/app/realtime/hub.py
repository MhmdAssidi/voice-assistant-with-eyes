"""In-memory event hub (owner: Student B, S0 + B11).

Keeps the open WebSocket connections and broadcasts every Event to all of
them (dashboard and phone). It also remembers WHEN things last happened, so
/api/status can tell "connected" from "silent for too long".
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import WebSocket

from app.contracts import Event

log = logging.getLogger(__name__)


class EventHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.last_ingest_status: Event | None = None
        self.last_ingest_at: datetime | None = None  # when we RECEIVED it (our clock)
        self.last_frame_at: datetime | None = None  # captured_at of the newest stored frame
        self.last_question_at: datetime | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def publish(self, event: Event) -> None:
        self._remember(event)
        message = event.model_dump_json()
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:  # a closed socket must never break the broadcast
                log.info("Dropping a disconnected WebSocket client")
                await self.disconnect(ws)

    def _remember(self, event: Event) -> None:
        if event.type == "ingest_status":
            self.last_ingest_status = event
            # Our own clock, not the worker's: a frozen worker must look silent.
            self.last_ingest_at = datetime.now(UTC)
        elif event.type == "frame_stored":
            captured = event.data.get("captured_at")
            if isinstance(captured, str):
                self.last_frame_at = datetime.fromisoformat(captured)
        elif event.type == "question_answered":
            asked = event.data.get("asked_at")
            if isinstance(asked, str):
                self.last_question_at = datetime.fromisoformat(asked)

    def ingest_is_fresh(self, max_age_s: float, now: datetime | None = None) -> bool:
        """True if an ingest_status arrived in the last max_age_s seconds."""
        if self.last_ingest_at is None:
            return False
        now = now or datetime.now(UTC)
        return (now - self.last_ingest_at).total_seconds() <= max_age_s

    @property
    def client_count(self) -> int:
        return len(self._clients)


hub = EventHub()
