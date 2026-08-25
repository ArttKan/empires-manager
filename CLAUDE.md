# CLAUDE.md

Instructions for Claude Code working in this repository. This file is authoritative
for agent behaviour and supersedes `AGENTS.md` where the two disagree.

## What this project is

A Tkinter desktop app for tracking scores in a game of the **Mega Empires** board
game (The West and/or The East), for **3–18 players**. The laptop is plugged into a
big TV, so every player must see the whole standings on one 1920 × 1080 screen with
no scrolling.

It is a private tool for one gaming group (usual size 14–16 players). It is never
published or distributed. Practicality during a live game beats defensive
validation and general-purpose architecture. The main risk to protect against is
**entering data for the wrong player**, not malformed input.

The full spec is `PROJEKTI.md` (Finnish); the end-user manual is `KAYTTOOHJE.md`
(Finnish). Both are current — read the relevant section before changing behaviour
they describe.

**In progress:** conversion to a client/server system so players can enter their
own data from phones. See "Backend conversion" below.

## Language policy

| Context | Language |
|---|---|
| Conversation with the user | **English** (user's explicit instruction, overrides `AGENTS.md`) |
| This file | English |
| All user-visible GUI strings, desktop and PWA | **English** — must match the rulebooks and printed components |
| Source code comments and docstrings | **Finnish** — match the existing style |
| `PROJEKTI.md`, `KAYTTOOHJE.md`, `deploy/README.md`, commit messages | **Finnish** |

Domain terms stay in English everywhere (Civilization Advance, Census, A.S.T.,
Trade Cards Acquisition, Calamity, …) — they are printed on the components.

## Commands

```bash
python3 app.py                              # run the app (needs a display)
.venv/bin/python -m unittest discover -v    # all 223 tests
python3 -m unittest discover -v             # 148 tests; HTTP/remote tests skip
.venv/bin/python -m unittest tests.test_http
.venv/bin/uvicorn main:app --reload         # run the server locally
```

**Use `.venv/bin/python` to run the suite.** `tests/test_http.py` and `tests/test_remote.py` need
fastapi/uvicorn/httpx and skip themselves under bare `python3`, so a green bare run proves less than
it looks. Recreate the venv with `python3 -m venv .venv` and
`.venv/bin/pip install -r requirements.txt` (needs the `python3.14-venv` apt
package). The venv is for the **server only** — the desktop app and every
pure-logic module must keep running under bare `python3`.

Dev machine: Ubuntu 26.04, Python 3.14 as `python3` (there is no bare `python`).
The GUI needs the `python3-tk` apt package. `tests/test_ui.py` skips itself when
tkinter is missing, so the suite runs headless on the server too.

**The deployment target is Python 3.10** (Ubuntu 22.04) and is not being upgraded.
Do not use syntax or stdlib APIs newer than 3.10. Verify with
`ast.parse(source, feature_version=(3, 10))` when in doubt.

`KAYTTOOHJE.md` still documents PowerShell and Python 3.12 from the project's
Windows origin.

## Architecture

Pure-logic modules have no Tkinter import; all UI lives in `ui.py`. Keep it that
way — it is what makes the logic testable without a display, and it is what makes
the backend conversion tractable.

| Module | Responsibility |
|---|---|
| [mega_empires/data.py](mega_empires/data.py) | Immutable reference data: 18 civilizations, 51 Advances, credits, A.S.T. era boundaries, official scenario setups per player count |
| [mega_empires/models.py](mega_empires/models.py) | `GameState` / `PlayerState` dataclasses, JSON (de)serialisation, `normalize()` clamping |
| [mega_empires/scoring.py](mega_empires/scoring.py) | Score breakdown, ranking, tie-breaks, visible rank numbers |
| [mega_empires/ast_rules.py](mega_empires/ast_rules.py) | Basic A.S.T. era requirements, marker state (READY / BLOCKED / WARNING / FINISHED) |
| [mega_empires/credits.py](mega_empires/credits.py) | Colour credits, row-chain discounts, effective Advance purchase price |
| [mega_empires/sequence.py](mega_empires/sequence.py) | The 13 Sequence of Play phases and their computed player orders |
| [mega_empires/calamities.py](mega_empires/calamities.py) | Minor and Major Calamity reference data for the Sequence of Play view |
| [mega_empires/config.py](mega_empires/config.py) | Server URL and token from `~/.config/mega-empires/config.json`, env vars overriding per field |
| [mega_empires/remote.py](mega_empires/remote.py) | `RemoteGameService` — the app in **remote mode**, i.e. a client of the box (the app is never itself a server): the same interface over HTTP. **stdlib `urllib` only** — the desktop app must run without the venv |
| [mega_empires/service.py](mega_empires/service.py) | `GameService` interface + `LocalGameService`: the only thing allowed to mutate `GameState`. Validated commands, version counters, JSONL command log |
| [mega_empires/storage.py](mega_empires/storage.py) | Named JSON saves, atomic writes, save listing, data-directory resolution |
| [main.py](main.py) | FastAPI HTTP layer over `GameService`. Thin by design: routes, auth, error mapping, SSE fan-out. **No game logic here** |
| [mega_empires/ui.py](mega_empires/ui.py) | Tkinter app, now a **client of `GameService`**: new-game wizard, tabs (Scoreboard / A.S.T. / Sequence of Play), Advances, Details and calamity dialogs. By far the largest module |

## Domain rules that are easy to get wrong

- **Scoring** (rulebook 13c): 1 VP per city; 1/3/6 VP per Advance by cost band
  (<100 / 100–200 / >200); 5 VP per A.S.T. step; optional +5 VP end-game bonus.
  Card VP is always derived from `data.py`, never typed in by the user.
- **A.S.T. bonus is conditional.** It is confirmed manually in the Details dialog
  during the final A.S.T. phase, never inferred from a Late Iron Age position.
  12+ players: at most two recipients, and they must be in different trade blocks.
  This lives in `service.validate_ast_bonus()` only; the duplicate that was in
  `PlayerDialog._save` has been deleted. Do not reintroduce rule checks in dialogs.
- **Era boundaries are per civilization and per scenario.** Read them through
  `basic_ast_era_starts(civilization, player_count, game_mode)`, never straight
  from `BASIC_AST_ERA_STARTS` — the 3-player East game shifts Parthia's MBA start.
- **`ADVANCE_CHAINS` is derived positionally** — `data.py` slices `ADVANCES` into
  consecutive triples, so each row of `_ADVANCE_ROWS` is one 1 VP → 3 VP → 6 VP
  discount chain. **Reordering or inserting a row silently breaks the discount
  logic.** Append nothing to that tuple without re-checking the chains.
- **Starting colour credits depend on player count**: 10 per colour for 3 and 5
  players, 5 per colour for 4 and 6, none above that.
- **Trade block** is `WEST`, `EAST`, or `SINGLE` (10–11 players have no blocks).
  `default_block()` encodes the scenario exceptions where Assyria and Egypt sit in
  the other block.
- **Player identity is always `Civilization (nickname)`** — e.g. `Hellas (Matti)`.
  Use `PlayerState.display_name` everywhere, including generated player orders.
- **Scoreboard rows stay in fixed A.S.T.-ranking order** (`players_in_ast_order`)
  so rows never jump around mid-game; the large badge shows the current rank from
  `visible_rankings`. Do not re-sort rows by score. That stability is what allows
  the rows to be built once and updated in place — see below.
- **Tie-breaks** follow the official list only as far as stored data allows.
  Credit-token criteria (steps 4–5) are not tracked, so a tie that would need them
  must be shown as unresolved, never claimed as decided.
- **Colour is never the only signal** — name, civilization, and rank are always
  present as text.
- `ast_variant` is stored as `BASIC`/`EXPERT`, but only Basic is implemented;
  `ast_era_index()` raises on `EXPERT` by design.

## Working conventions

- **The UI never mutates state.** It calls a `GameService` command through
  `_run_command()`, which surfaces `RuleViolation` as a dialog and returns False so
  dialogs stay open on rejection. The service persists; there is no `_save()`.
- `self.game` in `ui.py` is a **render cache** — a snapshot copy, refreshed by
  `_refresh_state()`. Button lambdas capture stale copies, so commands look the
  current value up with `_player(civilization)` rather than trusting the closure.
- Call `normalize()` after editing state from outside the models; it clamps
  cities, A.S.T. step 0–15, census, and dedupes advances.
- The save format is `version: 5`; `GameState.from_dict` migrates older saves.
  Bump the version and add a migration branch if the schema changes.
- **`GameState.version` is the save format; `state_version` is the global command
  counter.** Do not confuse them. `PlayerState.version` is the per-player counter
  used for write-conflict detection.
- **Mutate state only through `GameService`.** Commands take absolute values plus
  an `expected_version`, never deltas — two concurrent `+1`s would both succeed.
  Commands return copies, never live references, because `RemoteGameService` will
  not be able to return a live object.
- **Never hardcode a save path.** `storage.data_directory()` resolves
  `MEGA_EMPIRES_DATA_DIR` at call time, falling back to the repo's `tallennukset/`.
  Resolution must stay at call time so systemd can set it before start.
- **Never rebuild the scoreboard by destroying widgets.** `_refresh_summary()`
  builds rows once into `self._row_widgets` and afterwards only reconfigures the
  labels whose text actually changed, comparing against a Python-side cache so an
  unchanged row costs zero Tcl calls. Destroy-and-rebuild cost ~490 widget
  create/destroy operations and **1401 ms per click at 18 players**; in-place
  update is 0.5 ms. Rows are rebuilt only when the set of civilizations changes.
- **Only the visible tab is redrawn.** `_refresh_all()` puts the others in
  `self._pending_tabs`; `_on_tab_changed` draws them when shown. A.S.T. and
  Sequence still rebuild wholesale (~34 ms and ~86 ms), which is fine when paid
  only on the tab you are looking at.
- **Row callbacks must not trust their closure.** Rows outlive many state changes,
  so the `player` captured at build time is a stale copy. Look the current value up
  with `_player(civilization)` — this applies to counters, the census field, and
  both dialog openers.
- **Tests must never touch the real save directory.** `save_game(game, None)` and
  `get_service()` both fall back to `storage.default_save_path()`, which on a dev
  machine is the repo's `tallennukset/`. Tests that opened a game with `path=None`
  silently overwrote a live save. Every test that persists must set
  `MEGA_EMPIRES_DATA_DIR` to a temp directory *and* pass an explicit path.
- Add tests to the matching `tests/test_*.py` for any logic change. UI tests
  construct objects via `object.__new__(MegaEmpiresApp)` and a bare `tk.Tcl()`
  interpreter to avoid opening a window — follow that pattern.
- Verify changes against 3-, 5-, 9-, 10-, and 18-player setups.

## Backend conversion

Converting to a self-hosted backend with phone clients. Context lives in
`mega-empires-phase-a-handoff.md`; deployment specifics in
[deploy/README.md](deploy/README.md).

**Deployed environment:** `olohuone-ubuntu`, Ubuntu 22.04, Python 3.10, headless.
App runs as the non-root `megaempires` user under systemd, exposed via Cloudflare
Tunnel at `empiresmanager.com` with no inbound ports open. SSH only over
Tailscale. Game data lives in `/var/lib/mega-empires/` via systemd
`StateDirectory`, deliberately outside the git checkout.

**Phase A and the deploy pipeline are complete and proven.** The box runs a git
checkout of this repo, and push-to-live has been verified with a real change.

Repo is `git@github.com:ArttKan/mega-empires-manager.git` (an older
`rautiaik/Mega-Empires` URL is stale). All backend work happens on the
`backend-sekoilu` branch; `master` stays untouched until the whole chain is proven.
`deploy.sh` defaults to that branch and the server checkout tracks it.

Deploying is: commit and push here, then on the box over Tailscale SSH run
`sudo -u megaempires /home/megaempires/mega-empires-backend/deploy/deploy.sh`.
It fetches, reinstalls dependencies only when `requirements.txt` changed, runs the
suite, and restarts **only if tests pass** — so a broken push cannot take the live
service down. On the box the run reports `skipped=1`, because `tests/test_ui.py`
skips itself where tkinter is absent; that is expected.

**systemd unit:** `deploy/mega-empires-backend.service` is the only version of
the unit — it holds no secrets, so it is tracked normally and reaches the box
through an ordinary deploy. The `ECHO_TOKEN` lives in
`/etc/mega-empires-backend.env` (root-owned, 0600), read by systemd before it
drops to the service user. `EnvironmentFile` is deliberately mandatory: a missing
file stops the service rather than letting it serve wrongly.

This replaced an earlier arrangement where the box's copy carried the token inline
under `git update-index --skip-worktree`, which silently prevented unit changes
from ever reaching the server. That migration has been completed on the box, so
unit changes now deploy normally — do not reintroduce a secret into the template.

**Phase B, in progress.** The plan: one game state on the box; the laptop runs the
full Tkinter app as a *client* of it (main hub, full authority); phones are narrow
clients for cities, census and possibly advances, scoped to their own civilization.
The laptop holds a render cache, never a second authoritative state — nothing ever
merges. Its offline fallback is "take over locally and become the new truth", not
two-way sync.

Done: `service.py` with `LocalGameService` (commands, version counters, JSONL
command log, A.S.T. bonus validation), and `ui.py` fully wired to it — all eight
mutation sites plus both dialogs now issue commands instead of mutating dataclasses.

Done also: [main.py](main.py) — real endpoints backed by `LocalGameService`.
Commands map to `POST /players/{civ}/…` and `POST /turn`; errors map to 404
unknown player, **409 with the current version**, 422 rule violation, 400
otherwise. A single `asyncio.Lock` serialises commands.

**`/events` carries no game data and needs no token** — only `{"state_version": N}`.
Browser `EventSource` cannot send an `Authorization` header, so rather than putting
a token in the query string the stream is just a "refetch now" signal and clients
pull `/state` with their token. This also makes "every reconnect pulls a fresh
snapshot" fall out for free. **Do not put game data on that stream.**

Done also: [mega_empires/remote.py](mega_empires/remote.py) and the desktop app's
remote mode. Set `MEGA_EMPIRES_SERVER` (and `MEGA_EMPIRES_TOKEN`) and `ui.py`
connects to the box instead of opening a local save; unset, it behaves exactly as
before. `tests/test_remote.py` drives `RemoteGameService` against a **real uvicorn
running the real app**, so `remote.py` and `main.py` cannot drift apart unnoticed.

Rules that fall out of remote mode and must not be undone:

- **`remote.py` is stdlib-only.** httpx exists in the venv but the desktop app
  must start under bare `python3`; that is what makes the offline fallback real.
- **The laptop polls, it does not subscribe.** `_poll()` on a `root.after()` timer
  compares `state_version` and redraws only on change — no SSE client, no threads
  in Tkinter. A failed poll backs off from 2 s to 15 s, because `urllib` blocks the
  mainloop and hammering a dead server would freeze the UI.
- **A lost connection is not a state change.** `ServiceUnavailable` keeps the
  current view; only `CommandError` subclasses that mean rejection surface as
  dialogs.
- **Never auto-retry a `VersionConflict`.** Retrying with the old value overwrites
  whatever the other device just wrote. `_run_command()` refreshes the view and
  tells the user instead.
- **Requests must send a `User-Agent`.** Cloudflare rejects urllib's default
  `Python-urllib/3.x` with a 403 (error 1010, "browser signature banned"), so every
  call would fail in production. `remote.py` sends an honest identifier — no browser
  spoofing needed, Cloudflare only bans that one signature. **The test suite cannot
  catch this class of bug**: tests talk to `127.0.0.1` and never traverse Cloudflare,
  so anything the edge does — UA filtering, rate limits, buffering — only shows up
  against the real host.
- **Census input is debounced** (`CENSUS_DEBOUNCE_MS`); without it each keystroke
  was one request, and typing "45" briefly published 4 to every other client.

**Remote mode is the default, local is the fallback.** `load_server_config()`
returns a server and the app connects to it; no config means local, so a fresh
checkout and the test suite still run offline.

- **The laptop mirrors server state to a local save** (`palvelinpeli.json`) each
  time `state_version` moves. Without it the offline fallback would be useless —
  the game is on the box, so falling back would start from nothing mid-game. On
  fallback the laptop's copy simply becomes the truth; nothing merges back.
- **The fallback preselects the mirror, it never opens it automatically.** The
  saved-game list is always shown so the user can pick a different save or start
  fresh — the program does not decide which game is being played. The banner
  names the reason the server was unavailable.
- **A 503 "no saved game" is not an outage.** The server is reachable but empty,
  so the right response is the new-game wizard, not the offline prompt.
- **`POST /game`** installs a wizard-built `GameState` and swaps the cached
  service, so changing games needs no SSH and no restart. Version counters are
  reset on install so a new game cannot inherit the old one's.
- **The server has exactly one game**, at `MEGA_EMPIRES_DATA_DIR/nykyinen_peli.json`.
  Named saves are a desktop-only concept; `main.py` never calls `list_saved_games()`.
  Dropping other `.json` files in the data directory does nothing.
- **`POST /game` archives the previous game first** (`nykyinen_peli-<timestamp>.json`)
  along with its `.jsonl` command log, because overwriting the one file the server
  reads would otherwise destroy a live game permanently. The log moves with its
  game — leaving it behind would splice two games into one audit trail.

**Phase C, mostly built.** [web/index.html](web/index.html) is the player app,
served at `/` so the only thing read aloud at the table is the bare domain. One
page, three states, switching on whether `localStorage` holds a token: code entry,
seat picker, then the player's own row with a Scoreboard tab.

- **Authorization is per civilization.** [mega_empires/tokens.py](mega_empires/tokens.py)
  mints a token per civilization plus one join code, in a **separate `tokens.json`,
  never in `GameState`** — putting secrets there would copy them into every save,
  the command log directory, and the laptop's mirror. Written `0600`, compared with
  `secrets.compare_digest`.
- **Phones may change cities, census and advances on their own row only.** A.S.T.
  step, bonus, details, turn and new game are admin-only. 401 means "unknown
  token", 403 means "known but not allowed" — the phone needs to tell those apart.
- **`/join` is gated by a spoken code** and rate limited (10 failures per 10
  minutes per IP, read from `CF-Connecting-IP` since everything arrives from the
  tunnel as 127.0.0.1). A wrong code is 403 and counts; an already-claimed seat is
  409 and does not — a seat clash is a table mix-up, not an intrusion.
- **Seats are claimed exclusively.** Phone swaps, cleared browsers and dead
  batteries are handled by `POST /admin/release` from the laptop. There is
  deliberately **no player-side "leave"**: a button that releases your own seat
  can strand you mid-game, and every real case is involuntary anyway.
- **A new game mints new tokens and a new join code.** Players change civilization
  between games, so carrying tokens over would be wrong more often than right.
- **Phase gates** live in `sequence.PHASE_GATED_COMMANDS`: census in phase 2,
  advances in phase 12, cities ungated (it changes through conflict and calamities
  too, so a narrow window would block more corrections than it prevents mistakes).
  **Admin bypasses every gate** — the game master must be able to fix data without
  stepping the game backwards. `/state` reports the gates so the phone does not
  hold a second copy of the rule.
- **Scores and Advance prices are computed server-side** and returned by `/state`
  and `GET /players/{civ}/advances`. Reimplementing the VP bands or the colour
  credits and row-chain discounts in JavaScript would duplicate `scoring.py` and
  `credits.py`, and the two would drift silently until someone disputed a score.
- **Advance selections are held locally until Save**, and the list order is fixed
  when the sheet opens — re-sorting on every tap would move the next card out from
  under the player's thumb.

Remaining: the manifest and service worker for home-screen install, and the lobby
view in the desktop app (join code and claim status on the TV, release a seat).

**No browser TV display.** The laptop drives the TV with the Tkinter views, which
removed the largest piece of Phase C. Mobile browsers drop SSE when the screen
locks, so the phone refetches on `visibilitychange` and on a 15 s fallback poll as
well as on the stream — the stream alone would leave stale numbers after every
unlock.

FastAPI + uvicorn is the intended server stack. This breaks the project's former
stdlib-only rule, which was a deliberate decision — but the **desktop app and all
pure-logic modules must stay stdlib-only** so they keep running without the venv.

## Out of scope (do not build unasked)

Trade card hands or trading, automatic calamity resolution, map/token/ship
tracking, accounts or cloud storage, hardening against hand-edited save files, and
games outside 3–18 players.
