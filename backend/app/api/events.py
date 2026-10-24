"""WS /ws/events and POST /api/internal/events (owner: Student B).

- Student A's ingest worker POSTs events here (localhost only).
- The dashboard and the phone listen on the WebSocket.
"""

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.contracts import Event
from app.realtime.hub import hub

router = APIRouter(tags=["events (Student B)"])

# "testclient" is the host name FastAPI's TestClient uses in our tests.
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@router.post("/api/internal/events")
async def post_event(event: Event, request: Request) -> dict:
    client_host = request.client.host if request.client else ""
    if client_host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="Internal endpoint: localhost only")
    await hub.publish(event)
    return {"ok": True}


@router.websocket("/ws/events")
async def events_socket(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # we only push; reading detects disconnects
    except WebSocketDisconnect:
        await hub.disconnect(ws)
