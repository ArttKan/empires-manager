"""Mega Empires backend — HTTP-kerros.

Ohut kerros `GameService`-komentojen päälle. Täällä ei ole pelilogiikkaa: reitit
kääntävät HTTP:n komennoiksi, tarkistavat tokenin ja lähettävät muutosilmoituksen
kuunteleville asiakkaille. Säännöt ovat `src/service.py`:ssä, jotta ne
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

**Miksi /events on ilman tokenia:** selaimen `EventSource` ei osaa lähettää
Authorization-otsaketta. Sen sijaan että token ujutettaisiin kyselyparametriin,
virta ei kuljeta pelidataa lainkaan — vain uuden `state_version`-numeron. Asiakas
hakee varsinaisen tilan `/state`-reitiltä tokenilla. Sivutuotteena tämä toteuttaa
myös säännön "jokainen uudelleenyhteys hakee tuoreen tilannekuvan".
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

# ECHO_TOKEN on Phase A:n nimi. Uusi nimi on kuvaavampi, mutta vanha kelpaa yhä,
# jottei palvelimen /etc/mega-empires-backend.env vaadi samanaikaista muutosta.
TOKEN = os.environ.get("MEGA_EMPIRES_TOKEN") or os.environ.get("ECHO_TOKEN")

HEARTBEAT_SECONDS = 15
JOIN_MAX_FAILURES = 10
JOIN_WINDOW_SECONDS = 600
_join_failures: dict = {}

_service: Optional[LocalGameService] = None
_tokens: Optional[TokenStore] = None
_lock = asyncio.Lock()
_subscribers: "set[asyncio.Queue]" = set()

# HUOM sammutuksesta: `/events` on ääretön vastaus, ja uvicorn odottaa kesken
# olevien vastausten valmistumista ennen poistumista. Yksikin auki oleva puhelin
# jumittaa siis `systemctl restart`in. Tätä **ei voi korjata sovelluksesta**:
# uvicorn ajaa lifespan-sammutuksen vasta pyyntöjen valuttamisen jälkeen, joten
# käsittelijä joka sulkisi virrat odottaa itse niiden sulkeutumista.
# Ratkaisu on ExecStartin --timeout-graceful-shutdown; ks. deploy/README.md.
app = FastAPI(title="Mega Empires backend")


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


def get_token_store() -> TokenStore:
    """Lataa tai luo pelaajakohtaiset tokenit.

    Luodaan tarvittaessa nykyisen pelin sivilisaatioista, jotta myös käsin
    palvelimelle kopioitu peli saa tokenit ilman erillistä askelta.
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
    """Tunnista kutsuja adminiksi tai pelaajaksi.

    401 tarkoittaa "en tiedä kuka olet", 403 "tiedän, mutta et saa". Ne on
    pidettävä erillään, jotta puhelin osaa erottaa vanhentuneen tokenin
    väärään riviin koskemisesta.
    """

    if not TOKEN:
        # Sulkeudu, älä avaudu: konfiguroimaton token ei saa tarkoittaa
        # tunnistautumatonta pääsyä.
        raise HTTPException(
            status_code=500, detail="Server token is not configured"
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("Bearer "):].strip()

    try:
        store = get_token_store()
    except HTTPException:
        # Peliä ei ole, joten pelaajatokeneita ei voi olla. Admin kelpaa yhä.
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
    """Estä puhelimelta komennot väärässä vaiheessa.

    Kannettava ja korotettu puhelin ohittavat portin: pelinjohtajan on voitava
    korjata virhe milloin tahansa ilman että peliä siirretään vaiheissa
    taaksepäin.
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


@app.get("/state")
async def state(principal: Principal = Depends(get_principal)) -> dict:
    """Koko pelitila. Luettavissa myös pelaajatokenilla.

    Peli on avoimen informaation peli — pistetilanne on TV:llä kaikkien
    nähtävissä — joten rivien piilottaminen puhelimilta ei suojaisi mitään.
    Kirjoitusoikeus on eri asia ja rajattu erikseen.
    """

    game = get_service().snapshot()
    data = game.to_dict()
    # Pisteet lasketaan palvelimella eikä asiakkaassa. Muuten VP-säännöt ja
    # korttien hintaluokat olisivat olemassa sekä Pythonissa että
    # JavaScriptissä, ja ne ehtisivät erkaantua ennen kuin kukaan huomaa —
    # riita pistetilanteesta pöydässä on huono paikka löytää se.
    rankings = visible_rankings(game.players)
    # Ladataan luomatta: lukupyyntö ei saa luoda tokeneita sivuvaikutuksena.
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
        # Värit tulevat pelikomponentista (data.py). Asiakas ei saa arvata
        # niitä: pöydässä pelaaja tunnistaa itsensä juuri väristä.
        civilization = CIVILIZATION_BY_NAME[player.civilization]
        entry["color"] = civilization.color
        entry["text_color"] = civilization.text_color
        # Onko paikka varattu puhelimelta. Mukana tässä eikä erillisenä
        # kutsuna, koska pistetaulu on näkyvissä lähes koko ajan ja toinen
        # pyyntö joka kyselyllä olisi turhaa liikennettä.
        entry["claimed"] = bool(claims.get(player.civilization))
    data["phase_gates"] = {
        command: sorted(phases)
        for command, phases in PHASE_GATED_COMMANDS.items()
    }
    # Kuka kysyi. Puhelin ei voi päätellä korotustaan mistään muualta, eikä
    # sitä saa säilöä pelkkään localStorageen: vapautus ei silloin purkaisi
    # käyttöliittymää, vaikka palvelin kieltäytyisikin kirjoituksista.
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
    """Advance-kortit hintoineen tälle pelaajalle.

    Hinnat lasketaan palvelimella, koska ne riippuvat värikrediiteistä ja
    referenssitaulukon rivialennuksista — `credits.py`:n logiikasta, jota ei
    haluta toistaa JavaScriptissä. Luettavissa millä tahansa kelvollisella
    tokenilla; hinnat johtuvat tilasta joka on muutenkin näkyvissä.
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
    # Alennukset lasketaan vain aiempien kierrosten korteista: hankintavaihe on
    # yhtäaikainen, joten saman kierroksen ostot eivät alenna toisiaan silloinkaan
    # kun pelaaja kirjaa ne useassa erässä.
    discounting = discount_advances(player, game.round_number)
    # Lukitus on käyttöliittymän vihje POSTin säännöstä, joten sen on
    # noudatettava samaa poikkeusta: kannettava ja korotettu puhelin saavat
    # purkaa aiempienkin kierrosten kortteja. Muuten lista estäisi sen mitä
    # palvelin ottaisi vastaan.
    locked = set() if principal.bypasses_gates else set(discounting)
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
                # Aiempien kierrosten kortit ovat pysyviä: niitä ei voi purkaa.
                "locked": advance.id in locked,
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
            # Aiempien kierrosten kortit ovat pysyviä. Vain kuluvan kierroksen
            # ostoja saa perua, jotta näppäilyvirheen voi korjata heti.
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
    require_admin(principal)
    """Asenna uusi peli ja korvaa nykyinen.

    Työpöytäsovelluksen uuden pelin velho tuottaa valmiin `GameState`-rakenteen,
    joten palvelimen ei tarvitse toistaa skenaariologiikkaa: se ottaa vastaan
    serialisoidun tilan ja ottaa sen käyttöön.

    Korvaa myös välimuistissa olevan palvelun, joten palvelua ei tarvitse
    käynnistää uudelleen — se oli aiemmin ainoa tapa vaihtaa peliä.
    """

    try:
        game = GameState.from_dict(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail=f"Not a valid game: {error}"
        )
    if not game.players:
        raise HTTPException(status_code=422, detail="A game needs players.")

    # Uusi peli alkaa versiosta 0, jottei vanhan pelin laskuri jää voimaan.
    game.state_version = 0
    for player in game.players:
        player.version = 0

    path = default_save_path()
    async with _lock:
        # Edellinen peli siirretään syrjään ennen korvaamista: palvelin lukee
        # vain yhtä tiedostoa, joten ilman tätä vahinkopainallus tuhoaisi
        # käynnissä olevan pelin pysyvästi.
        archived = archive_existing(path)
        service = LocalGameService(game, save_path=path)
        service.save()
        set_service(service)
        # Uusi peli, uudet tokenit ja uusi liittymiskoodi: pelaajat vaihtavat
        # sivilisaatiota pelien välillä, joten vanhojen kantaminen mukana
        # osuisi useammin väärin kuin oikein.
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
    # Yksi kenttä, kaksi kelpaavaa koodia: peli- tai admin-koodi. Jälkimmäinen
    # varaa paikan samalla tavalla ja merkitsee sen lisäksi korotetuksi.
    code: str
    civilization: str = ""


class ReleaseBody(BaseModel):
    civilization: str


def _client_key(request: Request) -> str:
    # Cloudflare-tunnelin takana request.client on aina 127.0.0.1, joten
    # oikea osoite luetaan edgen otsakkeesta kun se on saatavilla.
    return (
        request.headers.get("cf-connecting-ip")
        or (request.client.host if request.client else "unknown")
    )


def _check_join_rate(request: Request) -> None:
    """Rajoita väärien koodien arvailua.

    Liittymiskoodi on lyhyt, koska se luetaan ääneen. Se kestää arvailua vain
    jos yrityksiä rajoitetaan.
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
    """Sivilisaatio -> pelin perustuksessa annettu nimi.

    Paikan valinta on juuri se hetki jolloin väärä rivi valitaan, joten
    nimi näytetään värin rinnalla: se on vahvin tunniste pöydässä.
    """

    try:
        game = get_service().snapshot()
    except HTTPException:
        return {}
    return {player.civilization: player.nickname for player in game.players}


@app.post("/join/roster")
async def join_roster(body: JoinBody, request: Request) -> dict:
    """Kerro mitkä paikat ovat vapaana. Koodi vaaditaan jo tähän.

    Ilman koodia kuka tahansa domainin löytänyt näkisi pelin kokoonpanon ja
    voisi seurata milloin paikkoja vapautuu.
    """

    _check_join_rate(request)
    store = get_token_store()
    kind = store.code_kind(body.code)
    if not kind:
        _record_join_failure(request)
        raise HTTPException(status_code=403, detail="Wrong join code.")
    nicknames = _nicknames()
    return {
        # Kerrotaan jo tässä kumman koodin liittyjä antoi, jotta hän näkee sen
        # ennen paikan varaamista eikä vasta jälkeenpäin.
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
    """Varaa sivilisaatio ja palauta sen token."""

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
        # Väärä koodi ja varattu paikka on erotettava toisistaan: jälkimmäinen
        # on tavallinen tilanne pöydässä, ei tunkeutumisyritys.
        raise HTTPException(status_code=409, detail=message)
    return {
        "token": token,
        "civilization": body.civilization,
        "elevated": store.is_elevated(body.civilization),
    }


@app.get("/admin/join")
async def admin_join(principal: Principal = Depends(get_principal)) -> dict:
    """Liittymiskoodi ja kuka on jo mukana. Kannettavan aulanäkymää varten."""

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
    """Vapauta paikka uudelleen varattavaksi.

    Tarvitaan kun puhelin vaihtuu tai selaimen tiedot tyhjenevät: muuten
    pelaaja lukittuisi ulos omasta rivistään kesken pelin.
    """

    require_admin(principal)
    store = get_token_store()
    try:
        store.release(body.civilization)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {"civilization": body.civilization, "claimed": False}


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


WEB_DIRECTORY = Path(__file__).resolve().parent / "web"


@app.get("/", response_class=HTMLResponse)
async def player_app() -> HTMLResponse:
    """Pelaajien sivu.

    Yksi sivu, joka näyttää liittymislomakkeen tai oman rivin sen mukaan onko
    selaimessa tallennettu token. Näin pöydässä luetaan ääneen vain domain,
    ei polkua sen perässä.

    `no-store`, koska sivu päivittyy tiheästi eikä siinä ole versioituja
    tiedostonimiä. Ilman sitä selain käyttää heuristista välimuistia ja puhelin
    voi jäädä pyörittämään vanhaa versiota pitkäksi aikaa — ja koska koko
    sovellus on yksi tiedosto, se tarkoittaa koko sovellusta.
    """

    html = (WEB_DIRECTORY / "index.html").read_text(encoding="utf-8")
    # X-Build kertoo mikä versio asiakkaalle meni. Sivu on yksi versioimaton
    # tiedosto, joten ilman tätä ei voi todeta ajaako puhelin nykyistä koodia.
    build = hashlib.sha256(html.encode("utf-8")).hexdigest()[:8]
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, must-revalidate",
            "X-Build": build,
        },
    )


