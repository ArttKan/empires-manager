"""Mega Empires backend — the HTTP layer.

A thin layer over the `GameService` commands. There is no game logic here: the
routes translate HTTP into commands, check the token and notify listening
clients of changes. The rules live in `src/service.py`, so that they hold for
the desktop app as well.

Routes:
  GET  /health                      liveness, no token
  GET  /events                      SSE change notifications, no token (below)
  GET  /state                       the whole game state, token
  POST /players/{civ}/cities        token
  POST /players/{civ}/census        token
  POST /players/{civ}/ast-step      token
  POST /players/{civ}/ast-bonus     token
  POST /players/{civ}/advances      token
  POST /players/{civ}/details       token
  POST /turn                        token

**Why /events takes no token:** a browser's `EventSource` cannot send an
Authorization header. Rather than smuggling the token into a query parameter,
the stream carries no game data at all — only the new `state_version` number.
The client then fetches the actual state from `/state` with its token. As a
side effect this also implements the rule "every reconnect pulls a fresh
snapshot".
"""

import asyncio
import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from src.core.credits import (
    advance_price,
    color_credits,
    discount_advances,
    flexible_credit_entitlement,
)
from src.core.data import ADVANCES, CIVILIZATION_BY_NAME
from src.core.models import GameState
from src.core.scoring import calculate_score, visible_rankings
from src.core.sequence import PHASE_GATED_COMMANDS
from src.service import (
    CommandError,
    CommandResult,
    LocalGameService,
    RuleViolation,
    UnknownPlayer,
    VersionConflict,
)
from src.storage import (
    archive_existing,
    data_directory,
    default_save_path,
    load_game,
)
from src.server.tokens import ADMIN, Principal, TokenStore, tokens_path

# ECHO_TOKEN is the Phase A name. The new name is more descriptive, but the old
# one still works, so /etc/mega-empires-backend.env need not change in step.
TOKEN = os.environ.get("MEGA_EMPIRES_TOKEN") or os.environ.get("ECHO_TOKEN")

HEARTBEAT_SECONDS = 15
JOIN_MAX_FAILURES = 10
JOIN_WINDOW_SECONDS = 600
_join_failures: dict = {}

_service: Optional[LocalGameService] = None
_tokens: Optional[TokenStore] = None
_lock = asyncio.Lock()
_subscribers: "set[asyncio.Queue]" = set()

# NOTE on shutdown: `/events` is an infinite response, and uvicorn waits for
# in-flight responses to finish before exiting. A single open phone therefore
# hangs `systemctl restart`. This **cannot be fixed in the application**:
# uvicorn runs lifespan shutdown only after draining requests, so a handler
# that would close the streams is itself waiting on them.
# The fix is ExecStart's --timeout-graceful-shutdown; see deploy/README.md.
app = FastAPI(title="Mega Empires backend")


# --------------------------------------------------------------------------
# The service and authentication
# --------------------------------------------------------------------------


def get_service() -> LocalGameService:
    """Load the game from disk on the first call.

    Loading is lazy rather than at startup, so the service comes up even when
    there is no save yet. A game is created with the desktop app; creating one
    over HTTP arrives with RemoteGameService.
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
    """For the tests and for reloading."""

    global _service
    _service = service


def get_token_store() -> TokenStore:
    """Load or create the per-player tokens.

    Created if needed from the current game's civilizations, so that a game
    copied to the server by hand also gets tokens without a separate step.
    """

    global _tokens
    if _tokens is None:
        path = tokens_path(data_directory())
        store = TokenStore.load(path)
        if store is None:
            game = get_service().snapshot()
            store = TokenStore.create(
                [player.civilization for player in game.players], path
            )
        _tokens = store
    return _tokens


def set_token_store(store: "Optional[TokenStore]") -> None:
    global _tokens
    _tokens = store


def get_principal(authorization: str = Header(default="")) -> Principal:
    """Identify the caller as an admin or a player.

    401 means "I do not know who you are", 403 means "I do, but you may not".
    They must be kept apart so a phone can tell a stale token from touching the
    wrong row.
    """

    if not TOKEN:
        # Fail closed, not open: an unconfigured token must never mean
        # unauthenticated access.
        raise HTTPException(
            status_code=500, detail="Server token is not configured"
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("Bearer "):].strip()

    try:
        store = get_token_store()
    except HTTPException:
        # There is no game, so there can be no player tokens. Admin still works.
        if token and TOKEN and secrets.compare_digest(token, TOKEN):
            return Principal("admin")
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    principal = store.principal_for(token, TOKEN)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return principal


def authorize(principal: Principal, civilization: str, command: str) -> None:
    if not principal.may_command(civilization, command):
        raise HTTPException(
            status_code=403,
            detail=(
                f"A player token for {principal.civilization or '?'} cannot "
                f"change {command} for {civilization}."
            ),
        )


PHASE_LABELS = {
    "census": "Census is counted in phase 2",
    "advances": "Civilization Advances are bought in phase 12",
}


def check_phase(principal: Principal, command: str) -> None:
    """Block a phone's commands in the wrong phase.

    The laptop and an elevated phone bypass the gate: the game master must be
    able to correct a mistake at any time without stepping the game backwards.
    """

    allowed = PHASE_GATED_COMMANDS.get(command)
    if allowed is None or principal.bypasses_gates:
        return
    phase = get_service().snapshot().current_phase
    if phase not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"{PHASE_LABELS[command]}. The game is in phase {phase}.",
        )


def require_admin(principal: Principal) -> None:
    if not principal.is_admin:
        raise HTTPException(
            status_code=403, detail="This action requires the admin token."
        )


# --------------------------------------------------------------------------
# Running commands and notifying of changes
# --------------------------------------------------------------------------


async def broadcast(state_version: int) -> None:
    for queue in list(_subscribers):
        queue.put_nowait(state_version)


async def execute(command: Callable[[], CommandResult]) -> dict:
    """Run a command, map errors to status codes and broadcast the change.

    The lock serialises writes. There is one writing process, so this is enough
    and no distributed locking is needed.
    """

    async with _lock:
        try:
            result = command()
        except UnknownPlayer as error:
            raise HTTPException(status_code=404, detail=str(error))
        except VersionConflict as error:
            # The client must fetch fresh state; an automatic retry with the old value
            # would overwrite the very change that caused the conflict.
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
# Request bodies
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


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "game_loaded": _service is not None,
    }


@app.get("/state")
async def state(principal: Principal = Depends(get_principal)) -> dict:
    """The whole game state. Readable with a player token too.

    This is a game of open information — the score is on the TV for everyone to
    see — so hiding rows from phones would protect nothing. Write access is a
    different matter and is restricted separately.
    """

    game = get_service().snapshot()
    data = game.to_dict()
    # Scores are computed on the server, not in the client. Otherwise the VP
    # rules and the card price bands would exist in both Python and JavaScript,
    # and would drift apart before anyone noticed — an argument about the score
    # at the table is a poor place to discover that.
    rankings = visible_rankings(game.players)
    # Load without creating: a read must not mint tokens as a side effect.
    store = TokenStore.load(tokens_path(data_directory()))
    claims = dict(store.status()) if store is not None else {}
    for entry, player in zip(data["players"], game.players):
        score = calculate_score(player)
        entry["score"] = {
            "cities": score.cities,
            "ast": score.ast,
            "advances": score.advances,
            "bonus": score.bonus,
            "total": score.total,
        }
        entry["rank"] = rankings[player.civilization]
        # The colours come from the game component (data.py). The client must not
        # guess them: at the table a player recognises themselves by the colour.
        civilization = CIVILIZATION_BY_NAME[player.civilization]
        entry["color"] = civilization.color
        entry["text_color"] = civilization.text_color
        # Whether a phone has claimed the seat. Included here rather than as a
        # separate call, because the scoreboard is on screen nearly all the time and
        # a second request on every poll would be wasted traffic.
        entry["claimed"] = bool(claims.get(player.civilization))
    data["phase_gates"] = {
        command: sorted(phases)
        for command, phases in PHASE_GATED_COMMANDS.items()
    }
    # Who asked. A phone cannot work out its elevation from anywhere else, and it
    # must not be kept in localStorage alone: releasing a seat would then not
    # undo the UI, even though the server would refuse the writes.
    data["you"] = {
        "civilization": principal.civilization,
        "elevated": principal.elevated,
        "admin": principal.is_admin,
    }
    return data


@app.get("/players/{civilization}/advances")
async def advance_catalogue(
    civilization: str,
    principal: Principal = Depends(get_principal),
) -> dict:
    """The Advances with their prices for this player.

    Prices are computed on the server because they depend on colour credits and
    the reference table's row discounts — the logic in `credits.py`, which we
    do not want to repeat in JavaScript. Readable with any valid token; the
    prices follow from state that is visible anyway.
    """

    game = get_service().snapshot()
    player = next(
        (p for p in game.players if p.civilization == civilization), None
    )
    if player is None:
        raise HTTPException(
            status_code=404, detail=f"No player for civilization {civilization!r}."
        )

    owned = set(player.advances)
    # Discounts come only from earlier turns' cards: the acquisition phase is
    # simultaneous, so same-turn purchases do not discount each other even when
    # the player records them in several batches.
    discounting = discount_advances(player, game.round_number)
    # The lock is the UI's hint about the POST rule, so it has to honour the same
    # exception: the laptop and an elevated phone may unpick cards from earlier
    # turns too. Otherwise the list would forbid what the server would accept.
    #
    locked = set() if principal.bypasses_gates else set(discounting)
    # When the card was bought. A different thing from `locked`, which says only
    # whether it may be undone: on an elevated phone nothing is locked, but the
    # list's grouping still needs to know when it was bought.
    bought_now = set(player.advances) - set(discounting)
    totals = color_credits(player, game.player_count, owned=discounting)
    entries = []
    for advance in ADVANCES:
        price = advance_price(
            advance, player, game.player_count, owned=discounting
        )
        entries.append(
            {
                "id": advance.id,
                "name": advance.name,
                "cost": advance.cost,
                "vp": advance.victory_points,
                "groups": list(advance.groups),
                "owned": advance.id in owned,
                # Cards from earlier turns are permanent: they cannot be unpicked.
                "locked": advance.id in locked,
                "this_turn": advance.id in bought_now,
                "effective_cost": price.effective_cost,
                "color_discount": price.color_discount,
                "row_discount": price.special_discount,
                "applied_group": price.applied_group,
            }
        )
    return {
        "civilization": civilization,
        "credits": totals,
        "flexible_total": flexible_credit_entitlement(list(player.advances)),
        "flexible_allocated": dict(player.flexible_credits),
        "advances": entries,
    }


@app.post("/players/{civilization}/cities")
async def set_cities(
    civilization: str,
    body: IntValue,
    principal: Principal = Depends(get_principal),
) -> dict:
    authorize(principal, civilization, "cities")
    service = get_service()
    return await execute(
        lambda: service.set_cities(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/census")
async def set_census(
    civilization: str,
    body: IntValue,
    principal: Principal = Depends(get_principal),
) -> dict:
    authorize(principal, civilization, "census")
    check_phase(principal, "census")
    service = get_service()
    return await execute(
        lambda: service.set_census(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/ast-step")
async def set_ast_step(
    civilization: str,
    body: IntValue,
    principal: Principal = Depends(get_principal),
) -> dict:
    require_admin(principal)
    service = get_service()
    return await execute(
        lambda: service.set_ast_step(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/ast-bonus")
async def set_ast_bonus(
    civilization: str,
    body: BoolValue,
    principal: Principal = Depends(get_principal),
) -> dict:
    require_admin(principal)
    service = get_service()
    return await execute(
        lambda: service.set_ast_bonus(
            civilization, body.value, body.expected_version, body.actor
        )
    )


@app.post("/players/{civilization}/advances")
async def set_advances(
    civilization: str,
    body: AdvancesBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    authorize(principal, civilization, "advances")
    check_phase(principal, "advances")
    service = get_service()
    if not principal.bypasses_gates:
        game = service.snapshot()
        player = next(
            (p for p in game.players if p.civilization == civilization), None
        )
        if player is not None:
            # Cards from earlier turns are permanent. Only this turn's purchases may be
            # undone, so a mistyped entry can be fixed straight away.
            permanent = set(discount_advances(player, game.round_number))
            removed = permanent - set(body.advances)
            if removed:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Advances bought on earlier turns cannot be removed: "
                        + ", ".join(sorted(removed))
                    ),
                )
    return await execute(
        lambda: service.set_advances(
            civilization,
            body.advances,
            body.flexible_credits,
            body.expected_version,
            body.actor,
        )
    )


@app.post("/players/{civilization}/details")
async def set_player_details(
    civilization: str,
    body: DetailsBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require_admin(principal)
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


@app.post("/turn")
async def set_turn(
    body: TurnBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require_admin(principal)
    service = get_service()
    return await execute(
        lambda: service.set_turn(
            body.round_number,
            body.current_phase,
            body.expected_state_version,
            body.actor,
        )
    )


@app.post("/game")
async def create_game(
    payload: dict,
    principal: Principal = Depends(get_principal),
) -> dict:
    """Install a new game, replacing the current one.

    The desktop app's new-game wizard produces a complete `GameState`, so the
    server need not repeat the scenario logic: it accepts a serialised state
    and installs it.

    This also swaps the cached service, so the service does not need
    restarting — which used to be the only way to change games.
    """

    require_admin(principal)
    try:
        game = GameState.from_dict(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail=f"Not a valid game: {error}"
        )
    if not game.players:
        raise HTTPException(status_code=422, detail="A game needs players.")

    # A new game starts from version 0, so the old game's counter cannot carry over.
    game.state_version = 0
    for player in game.players:
        player.version = 0

    path = default_save_path()
    async with _lock:
        # The previous game is archived before it is replaced: the server reads one
        # file only, so without this a mistaken click would destroy a game in
        # progress for good.
        archived = archive_existing(path)
        service = LocalGameService(game, save_path=path)
        service.save()
        set_service(service)
        # A new game means new tokens and a new join code: players change
        # civilization between games, so carrying the old ones over would be wrong
        # more often than right.
        set_token_store(
            TokenStore.create(
                [player.civilization for player in game.players],
                tokens_path(data_directory()),
            )
        )
        version = service.snapshot().state_version

    await broadcast(version)
    return {
        "state_version": version,
        "player_count": game.player_count,
        "archived": archived.name if archived else None,
    }


class JoinBody(BaseModel):
    # One field, two acceptable codes: the game code or the admin code. The
    # latter claims a seat the same way and marks it elevated as well.
    code: str
    civilization: str = ""


class ReleaseBody(BaseModel):
    civilization: str


def _client_key(request: Request) -> str:
    # Behind the Cloudflare tunnel request.client is always 127.0.0.1, so the
    # real address is read from the edge's header when it is available.
    return (
        request.headers.get("cf-connecting-ip")
        or (request.client.host if request.client else "unknown")
    )


def _check_join_rate(request: Request) -> None:
    """Rate-limit guessing at the codes.

    The join code is short because it is read aloud. It only withstands
    guessing if the attempts are limited.
    """

    key = _client_key(request)
    now = time.monotonic()
    attempts = [
        stamp
        for stamp in _join_failures.get(key, [])
        if now - stamp < JOIN_WINDOW_SECONDS
    ]
    _join_failures[key] = attempts
    if len(attempts) >= JOIN_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Wait a few minutes and try again.",
        )


def _record_join_failure(request: Request) -> None:
    _join_failures.setdefault(_client_key(request), []).append(
        time.monotonic()
    )


def _nicknames() -> dict:
    """Civilization -> the nickname given when the game was set up.

    Picking a seat is the exact moment the wrong row gets chosen, so the name
    is shown alongside the colour: it is the strongest identifier at the table.
    """

    try:
        game = get_service().snapshot()
    except HTTPException:
        return {}
    return {player.civilization: player.nickname for player in game.players}


@app.post("/join/roster")
async def join_roster(body: JoinBody, request: Request) -> dict:
    """Report which seats are free. A code is required even for this.

    Without one, anyone who found the domain could see the game's line-up and
    watch for seats becoming free.
    """

    _check_join_rate(request)
    store = get_token_store()
    kind = store.code_kind(body.code)
    if not kind:
        _record_join_failure(request)
        raise HTTPException(status_code=403, detail="Wrong join code.")
    nicknames = _nicknames()
    return {
        # Report here which code was given, so the joiner sees it before claiming a
        # seat rather than after.
        "elevated": kind == ADMIN,
        "players": [
            {
                "civilization": name,
                "claimed": claimed,
                "color": CIVILIZATION_BY_NAME[name].color,
                "nickname": nicknames.get(name, ""),
            }
            for name, claimed in store.status()
        ]
    }


@app.post("/join")
async def join(body: JoinBody, request: Request) -> dict:
    """Claim a civilization and return its token."""

    _check_join_rate(request)
    store = get_token_store()
    try:
        token = store.claim(
            body.code,
            body.civilization,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    except ValueError as error:
        message = str(error)
        if "join code" in message:
            _record_join_failure(request)
            raise HTTPException(status_code=403, detail=message)
        # A wrong code and a taken seat must be told apart: the latter is an ordinary
        # situation at the table, not an intrusion attempt.
        raise HTTPException(status_code=409, detail=message)
    return {
        "token": token,
        "civilization": body.civilization,
        "elevated": store.is_elevated(body.civilization),
    }


@app.get("/admin/join")
async def admin_join(principal: Principal = Depends(get_principal)) -> dict:
    """The join code and who has joined. For the laptop's lobby view."""

    require_admin(principal)
    store = get_token_store()
    nicknames = _nicknames()
    return {
        "join_code": store.join_code,
        "admin_code": store.admin_code,
        "players": [
            {
                "civilization": name,
                "claimed": claimed,
                "nickname": nicknames.get(name, ""),
                "elevated": store.is_elevated(name),
            }
            for name, claimed in store.status()
        ],
    }


@app.post("/admin/release")
async def admin_release(
    body: ReleaseBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    """Free a seat to be claimed again.

    Needed when a phone is swapped or a browser's data is cleared: otherwise a
    player would be locked out of their own row mid-game.
    """

    require_admin(principal)
    store = get_token_store()
    try:
        store.release(body.civilization)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {"civilization": body.civilization, "claimed": False}


async def event_stream(request: Request):
    """The SSE stream, which carries only the new version number.

    It waits on a queue rather than spinning in a one-second loop as the Phase A
    version did. The heartbeat therefore goes out only when the stream is
    genuinely quiet, which is exactly when it is needed: during a game changes
    arrive in bursts with minutes between them.
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


WEB_DIRECTORY = Path(__file__).resolve().parent / "web"


@app.get("/", response_class=HTMLResponse)
async def player_app() -> HTMLResponse:
    """The players' page.

    One page, showing either the join form or the player's own row depending on
    whether the browser holds a token. That way only the bare domain is read
    aloud at the table, with no path after it.

    `no-store`, because the page changes often and has no versioned filenames.
    Without it the browser applies heuristic caching and a phone can keep
    running an old version for a long time — and since the whole app is one
    file, that means the whole app.
    """

    html = (WEB_DIRECTORY / "index.html").read_text(encoding="utf-8")
    # X-Build says which version reached the client. The page is one unversioned
    # file, so without it there is no way to tell whether a phone runs current code.
    build = hashlib.sha256(html.encode("utf-8")).hexdigest()[:8]
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, must-revalidate",
            "X-Build": build,
        },
    )


