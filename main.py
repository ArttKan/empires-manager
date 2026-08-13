"""
Mega Empires backend — Phase A skeleton.

Proves the pipe: box -> systemd -> Cloudflare Tunnel -> phone on cellular.
No real game logic here yet. That's Phase B, back in the repo.

Endpoints:
  GET  /health   -> liveness check, no auth
  GET  /state    -> hardcoded fake JSON, no auth (stands in for the real
                     game state fan-out later)
  GET  /events   -> SSE stream, no auth, heartbeat comment every 15s so
                     Cloudflare / mobile carriers don't reap the idle
                     connection (~100s timeout upstream)
  POST /echo     -> bearer-token gated, echoes back whatever JSON body
                     you send. Stands in for the future command endpoint.
"""

import asyncio
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Mega Empires backend — Phase A")

# Bearer token for the /echo endpoint. Set this in the systemd unit's
# Environment= line or an EnvironmentFile, never hardcode it here.
ECHO_TOKEN = os.environ.get("ECHO_TOKEN")

HEARTBEAT_SECONDS = 15

from fastapi.responses import HTMLResponse

@app.get("/sse-test", response_class=HTMLResponse)
async def sse_test():
    with open("sse-test.html") as f:
        return f.read()

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/state")
async def state():
    # Hardcoded fake payload — shape is illustrative only, not the real
    # GameState schema from models.py.
    return {
        "game_id": "fake-game-0001",
        "version": 12,
        "players": [
            {"name": "Alice", "civilization": "Hellas", "cities": 4},
            {"name": "Bob", "civilization": "Egypt", "cities": 3},
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def event_stream(request: Request):
    """
    Minimal SSE generator. Sends a heartbeat comment line (":\n\n") every
    HEARTBEAT_SECONDS so idle connections stay open through Cloudflare
    and flaky mobile carrier networks, plus an occasional real event so
    the phone-lock/unlock test has something to observe resuming.
    """
    counter = 0
    last_beat = time.monotonic()
    try:
        while True:
            if await request.is_disconnected():
                break

            now = time.monotonic()
            if now - last_beat >= HEARTBEAT_SECONDS:
                yield ":heartbeat\n\n"
                last_beat = now

            # A fake periodic event, just so there's something other than
            # heartbeats to see in the stream during manual testing.
            counter += 1
            yield f"event: tick\ndata: {counter}\n\n"

            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # Client disconnected; nothing to clean up in this skeleton.
        raise


@app.get("/events")
async def events(request: Request):
    return StreamingResponse(
        event_stream(request),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so events actually stream rather
            # than batching up behind Cloudflare/nginx buffers.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class EchoBody(BaseModel):
    message: str


def require_bearer_token(authorization: str | None):
    if not ECHO_TOKEN:
        # Fail closed: if the env var isn't set, refuse rather than
        # silently accepting unauthenticated requests.
        raise HTTPException(
            status_code=500, detail="ECHO_TOKEN not configured on server"
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != ECHO_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


@app.post("/echo")
async def echo(body: EchoBody, authorization: str | None = Header(default=None)):
    require_bearer_token(authorization)
    return {"you_sent": body.message, "received_at": datetime.now(timezone.utc).isoformat()}
