"""In-memory event hub (owner: Student B).

Keeps the open WebSocket connections and the latest ingest_status, and
broadcasts every Event to all connected clients (dashboard and phone).
Minimal S0 version; Student B extends it in B11.
"""

import asyncio
import logging

from fastapi import WebSocket

from app.contracts import Event

log = logging.getLogger(__name__)


class EventHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.last_ingest_status: Event | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def publish(self, event: Event) -> None:
        if event.type == "ingest_status":
            self.last_ingest_status = event
        message = event.model_dump_json()
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:  # a closed socket must never break the broadcast
                log.info("Dropping a disconnected WebSocket client")
                await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


hub = EventHub()
