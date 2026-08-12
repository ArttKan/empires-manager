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
| All user-visible GUI strings | **English** — must match the rulebooks and printed components |
| Source code comments and docstrings | **Finnish** — match the existing style |
| `PROJEKTI.md`, `KAYTTOOHJE.md`, `deploy/README.md`, commit messages | **Finnish** |

Domain terms stay in English everywhere (Civilization Advance, Census, A.S.T.,
Trade Cards Acquisition, Calamity, …) — they are printed on the components.

## Commands

```bash
python3 app.py                          # run the app (needs a display)
python3 -m unittest discover -v         # run all 65 tests
python3 -m unittest tests.test_scoring  # run one module
```

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
| [mega_empires/storage.py](mega_empires/storage.py) | Named JSON saves, atomic writes, save listing, data-directory resolution |
| [mega_empires/ui.py](mega_empires/ui.py) | Tkinter app: new-game wizard, tabs (Scoreboard / A.S.T. / Sequence of Play), Advances, Details and calamity dialogs. By far the largest module |

## Domain rules that are easy to get wrong

- **Scoring** (rulebook 13c): 1 VP per city; 1/3/6 VP per Advance by cost band
  (<100 / 100–200 / >200); 5 VP per A.S.T. step; optional +5 VP end-game bonus.
  Card VP is always derived from `data.py`, never typed in by the user.
- **A.S.T. bonus is conditional.** It is confirmed manually in the Details dialog
  during the final A.S.T. phase, never inferred from a Late Iron Age position.
  12+ players: at most two recipients, and they must be in different trade blocks.
  **This validation currently lives in `PlayerDialog._save` in `ui.py`** — it is
  the one piece of real game logic stranded in the UI layer, and Phase B moves it
  into the core.
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
  `visible_rankings`. Do not re-sort rows by score.
- **Tie-breaks** follow the official list only as far as stored data allows.
  Credit-token criteria (steps 4–5) are not tracked, so a tie that would need them
  must be shown as unresolved, never claimed as decided.
- **Colour is never the only signal** — name, civilization, and rank are always
  present as text.
- `ast_variant` is stored as `BASIC`/`EXPERT`, but only Basic is implemented;
  `ast_era_index()` raises on `EXPERT` by design.

## Working conventions

- Every mutation autosaves immediately: mutate the `PlayerState`, then call
  `_save_and_refresh()` (or `_save()` when the widget already shows the new value).
- Call `normalize()` after editing state from outside the models; it clamps
  cities, A.S.T. step 0–15, census, and dedupes advances.
- The save format is `version: 4`; `GameState.from_dict` migrates older saves.
  Bump the version and add a migration branch if the schema changes.
- **Never hardcode a save path.** `storage.data_directory()` resolves
  `MEGA_EMPIRES_DATA_DIR` at call time, falling back to the repo's `tallennukset/`.
  Resolution must stay at call time so systemd can set it before start.
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

**Phase A is complete** (tunnel, TLS, systemd, SSE verified from cellular).

All backend work happens on the `backend-sekoilu` branch; `master` stays untouched
until the whole chain is proven working. `deploy.sh` defaults to that branch and
the server checkout tracks it.

**Phase B, not yet started:** extract a `GameService` that owns the `GameState`
and exposes validated commands instead of letting callers mutate dataclasses;
per-player version counters; append-only JSONL command log. Move the A.S.T. bonus
validation out of `ui.py`. Wire one command end to end before filling in the rest.
Keep the Tkinter app working against `GameService` as a correctness check.

**Phase C, not designed:** browser TV display and a player PWA. Mobile browsers
drop SSE when the screen locks, so every client reconnect must pull a full fresh
snapshot rather than assuming it missed nothing.

FastAPI + uvicorn is the intended server stack. This breaks the project's former
stdlib-only rule, which was a deliberate decision — but the **desktop app and all
pure-logic modules must stay stdlib-only** so they keep running without the venv.

## Out of scope (do not build unasked)

Trade card hands or trading, automatic calamity resolution, map/token/ship
tracking, accounts or cloud storage, hardening against hand-edited save files, and
games outside 3–18 players.
