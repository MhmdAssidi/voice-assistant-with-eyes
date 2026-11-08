"""Lets the phone find this server on the local network (owner: Student B, polish).

The laptop's IP address changes with every network (two homes, a phone hotspot,
the demo room), and a blind user cannot be asked to type it. So the app shouts
"VAEYES_DISCOVER" as a UDP broadcast on every network it is connected to, and
this responder answers. The phone then uses the address the answer came from.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings

log = logging.getLogger("uvicorn.error")

REQUEST = b"VAEYES_DISCOVER"
API_PORT = 8000  # the port uvicorn is started with (see README)


def reply_for(data: bytes) -> bytes | None:
    """The answer to a datagram, or None if it is not a discovery request."""
    if data.strip() != REQUEST:
        return None
    return json.dumps({"service": "va-eyes", "api_port": API_PORT}).encode()


class _Responder(asyncio.DatagramProtocol):
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        reply = reply_for(data)
        if reply is not None:
            self.transport.sendto(reply, addr)  # type: ignore[attr-defined]
            log.info("discovery: answered %s", addr[0])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs the responder for as long as the API runs (FastAPI lifespan)."""
    transport = None
    try:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            _Responder, local_addr=("0.0.0.0", settings.discovery_port)
        )
        log.info("discovery: listening on UDP %d", settings.discovery_port)
    except OSError as error:
        # The API still works; the phone can use the address typed in Settings.
        log.warning("discovery disabled (UDP %d): %s", settings.discovery_port, error)
    try:
        yield
    finally:
        if transport is not None:
            transport.close()
