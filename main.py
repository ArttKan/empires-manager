"""Mega Empires backend — HTTP-kerros.

Ohut kerros `GameService`-komentojen päälle. Täällä ei ole pelilogiikkaa: reitit
kääntävät HTTP:n komennoiksi, tarkistavat tokenin ja lähettävät muutosilmoituksen
kuunteleville asiakkaille. Säännöt ovat `mega_empires/service.py`:ssä, jotta ne
pätevät myös työpöytäsovellukselle.

Reitit:
  GET  /health                      elossaolo, ei tokenia
  GET  /events                      SSE-muutosilmoitukset, ei tokenia (ks. alla)
  GET  /state                       koko pelitila, token
  POST /players/{civ}/cities        token
  POST /players/{civ}/census        token
  POST /players/{civ}/ast-step      token
  POST /players/{civ}/ast-bonus     token
  POST /players/{civ}/advances      token
  POST /players/{civ}/details       token
  POST /turn                        token
  POST /echo                        Phase A:n yhteystesti, token
  GET  /sse-test                    selaindiagnostiikka

**Miksi /events on ilman tokenia:** selaimen `EventSource` ei osaa lähettää
Authorization-otsaketta. Sen sijaan että token ujutettaisiin kyselyparametriin,
virta ei kuljeta pelidataa lainkaan — vain uuden `state_version`-numeron. Asiakas
hakee varsinaisen tilan `/state`-reitiltä tokenilla. Sivutuotteena tämä toteuttaa
myös säännön "jokainen uudelleenyhteys hakee tuoreen tilannekuvan".
"""

import asyncio
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from mega_empires.service import (
    CommandError,
    CommandResult,
    LocalGameService,
    RuleViolation,
    UnknownPlayer,
    VersionConflict,
)
from mega_empires.storage import default_save_path, load_game

app = FastAPI(title="Mega Empires backend")

# ECHO_TOKEN on Phase A:n nimi. Uusi nimi on kuvaavampi, mutta vanha kelpaa yhä,
# jottei palvelimen /etc/mega-empires-backend.env vaadi samanaikaista muutosta.
TOKEN = os.environ.get("MEGA_EMPIRES_TOKEN") or os.environ.get("ECHO_TOKEN")

HEARTBEAT_SECONDS = 15

_service: Optional[LocalGameService] = None
_lock = asyncio.Lock()
_subscribers: "set[asyncio.Queue]" = set()


# --------------------------------------------------------------------------
# Palvelu ja tunnistautuminen
# --------------------------------------------------------------------------


def get_service() -> LocalGameService:
    """Lataa peli levyltä ensimmäisellä kutsulla.

    Lataus on laiska eikä käynnistyksessä, jotta palvelu nousee myös silloin kun
    tallennusta ei vielä ole. Peli luodaan toistaiseksi työpöytäsovelluksella;
    luonti HTTP:n yli tulee RemoteGameServicen mukana.
    """

    global _service
    if _service is None:
        path = default_save_path()
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail=f"No saved game at {path}.",
            )
        _service = LocalGameService(load_game(path), save_path=path)
    return _service


def set_service(service: Optional[LocalGameService]) -> None:
    """Testien ja uudelleenlatauksen käyttöön."""

    global _service
    _service = service


def require_token(authorization: str = Header(default="")) -> None:
    if not TOKEN:
        # Sulkeudu, älä avaudu: konfiguroimaton token ei saa tarkoittaa
        # tunnistautumatonta pääsyä.
        raise HTTPException(
            status_code=500, detail="Server token is not configured"
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization[len("Bearer "):].strip() != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


# --------------------------------------------------------------------------
# Komentojen suoritus ja muutosilmoitukset
# --------------------------------------------------------------------------


async def broadcast(state_version: int) -> None:
    for queue in list(_subscribers):
        queue.put_nowait(state_version)


async def execute(command: Callable[[], CommandResult]) -> dict:
    """Suorita komento, käännä virheet statuskoodeiksi ja ilmoita muutoksesta.

    Lukko sarjallistaa kirjoitukset. Kirjoittavia prosesseja on yksi, joten tämä
    riittää eikä hajautettua lukitusta tarvita.
    """

    async with _lock:
        try:
            result = command()
        except UnknownPlayer as error:
            raise HTTPException(status_code=404, detail=str(error))
        except VersionConflict as error:
            # Asiakkaan on haettava tuore tila; automaattinen uudelleenyritys
            # vanhalla arvolla yliajaisi juuri sen muutoksen josta konflikti tuli.
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(error),
                    "expected_version": error.expected,
                    "current_version": error.actual,
                },
            )
        except RuleViolation as error:
            raise HTTPException(status_code=422, detail=str(error))
        except CommandError as error:
            raise HTTPException(status_code=400, detail=str(error))

    await broadcast(result.state_version)
    return {
        "state_version": result.state_version,
        "player": asdict(result.player) if result.player is not None else None,
    }


# --------------------------------------------------------------------------
# Pyyntörungot
# --------------------------------------------------------------------------


class IntValue(BaseModel):
    value: int
    expected_version: Optional[int] = None
    actor: str = "http"


class BoolValue(BaseModel):
    value: bool
    expected_version: Optional[int] = None
    actor: str = "http"


class AdvancesBody(BaseModel):
    advances: list[str]
    flexible_credits: Optional[dict] = None
    expected_version: Optional[int] = None
    actor: str = "http"


class DetailsBody(BaseModel):
    nickname: str
    block: str
    cities: int
    ast_step: int
    census: int
    ast_bonus: bool
    expected_version: Optional[int] = None
    actor: str = "http"


class TurnBody(BaseModel):
    round_number: int
    current_phase: int
    expected_state_version: Optional[int] = None
    actor: str = "http"


class EchoBody(BaseModel):
    message: str


# --------------------------------------------------------------------------
# Reitit
# --------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "game_loaded": _service is not None,
    }


@app.get("/state", dependencies=[Depends(require_token)])
async def state() -> dict:
    return get_service().snapshot().to_dict()


@app.post("/players/{civilization}/cities", dependencies=[Depends(require_token)])
async def set_cities(civilization: str, body: IntValue) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_cities(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/census", dependencies=[Depends(require_token)])
async def set_census(civilization: str, body: IntValue) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_census(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/ast-step", dependencies=[Depends(require_token)])
async def set_ast_step(civilization: str, body: IntValue) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_ast_step(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/ast-bonus", dependencies=[Depends(require_token)])
async def set_ast_bonus(civilization: str, body: BoolValue) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_ast_bonus(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/advances", dependencies=[Depends(require_token)])
async def set_advances(civilization: str, body: AdvancesBody) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_advances(
            civilization,
            body.advances,
            body.flexible_credits,
            body.expected_version,
            body.actor,
        )
    )


@app.post("/players/{civilization}/details", dependencies=[Depends(require_token)])
async def set_player_details(civilization: str, body: DetailsBody) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_player_details(
            civilization,
            nickname=body.nickname,
            block=body.block,
            cities=body.cities,
            ast_step=body.ast_step,
            census=body.census,
            ast_bonus=body.ast_bonus,
            expected_version=body.expected_version,
            actor=body.actor,
        )
    )


@app.post("/turn", dependencies=[Depends(require_token)])
async def set_turn(body: TurnBody) -> dict:
    service = get_service()
    return await execute(
        lambda: service.set_turn(
            body.round_number,
            body.current_phase,
            body.expected_state_version,
            body.actor,
        )
    )


@app.post("/echo", dependencies=[Depends(require_token)])
async def echo(body: EchoBody) -> dict:
    """Phase A:n yhteystesti. Säilytetty, koska deploy-ohje käyttää sitä."""

    return {
        "you_sent": body.message,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


async def event_stream(request: Request):
    """SSE-virta, joka kertoo vain uuden version numeron.

    Odottaa jonossa eikä pyöri sekunnin silmukassa kuten Phase A:n versio. Näin
    heartbeat lähtee vasta kun virta on oikeasti hiljainen, mikä on juuri se
    tilanne jossa se on tarpeen: pelin aikana muutoksia tulee purskeina ja
    väleissä voi olla minuutteja.
    """

    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)
    try:
        try:
            current = get_service().snapshot().state_version
        except HTTPException:
            current = None
        yield _state_event(current)
        while True:
            if await request.is_disconnected():
                break
            try:
                version = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_SECONDS
                )
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            yield _state_event(version)
    finally:
        _subscribers.discard(queue)


def _state_event(state_version: Optional[int]) -> str:
    payload = json.dumps({"state_version": state_version})
    return f"event: state\ndata: {payload}\n\n"


@app.get("/events")
async def events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sse-test", response_class=HTMLResponse)
async def sse_test() -> str:
    with open("sse-test.html", encoding="utf-8") as stream:
        return stream.read()
