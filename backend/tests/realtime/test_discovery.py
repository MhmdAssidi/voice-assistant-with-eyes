"""Server discovery tests (polish): the phone's UDP broadcast gets an answer."""

import asyncio
import json
import socket

from app.realtime import discovery


def test_reply_only_to_discovery_requests() -> None:
    reply = discovery.reply_for(b"VAEYES_DISCOVER\n")
    assert json.loads(reply) == {"service": "va-eyes", "api_port": 8000}
    assert discovery.reply_for(b"hello") is None
    assert discovery.reply_for(b"") is None


def test_responder_answers_over_udp(monkeypatch) -> None:  # noqa: ANN001
    # A free UDP port, so the test never clashes with a running server.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    monkeypatch.setattr(discovery.settings, "discovery_port", port)

    async def scenario() -> bytes:
        async with discovery.lifespan(None):  # type: ignore[arg-type]
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.setblocking(False)
            client.sendto(b"VAEYES_DISCOVER", ("127.0.0.1", port))
            loop = asyncio.get_running_loop()
            try:
                return await asyncio.wait_for(loop.sock_recv(client, 1024), timeout=3)
            finally:
                client.close()

    answer = asyncio.run(scenario())
    assert json.loads(answer)["service"] == "va-eyes"
