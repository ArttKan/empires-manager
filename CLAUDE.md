# CLAUDE.md

Instructions for Claude Code working in this repository. This file is authoritative
for agent behaviour and supersedes `AGENTS.md` where the two disagree.

## What this project is

A local Tkinter desktop app for tracking scores in a large combined game of the
**Mega Empires** board game (The West + The East), for 5–18 players. The laptop is
plugged into a big TV, so every player must see the whole standings on one
1920 × 1080 screen with no scrolling.

It is a private tool for one gaming group. It is never published or distributed.
Practicality during a live game beats defensive validation and general-purpose
architecture. The main risk to protect against is **entering data for the wrong
player**, not malformed input.

The full spec is `PROJEKTI.md` (Finnish); the end-user manual is `KAYTTOOHJE.md`
(Finnish). Both are current — read the relevant section before changing behaviour
they describe.

## Language policy

| Context | Language |
|---|---|
| Conversation with the user | **English** (user's explicit instruction, overrides `AGENTS.md`) |
| This file | English |
| All user-visible GUI strings | **English** — must match the rulebooks and printed components |
| Source code comments and docstrings | **Finnish** — match the existing style |
| `PROJEKTI.md`, `KAYTTOOHJE.md`, commit messages | **Finnish** |

Domain terms stay in English everywhere (Civilization Advance, Census, A.S.T.,
Trade Cards Acquisition, …) — they are printed on the components.

## Commands

```bash
python3 app.py                        # run the app (needs a display)
python3 -m unittest discover -v       # run all 34 tests
python3 -m unittest tests.test_scoring # run one module
```

Environment: Ubuntu 26.04, Python 3.14 as `python3` (there is no bare `python`).
The GUI requires the `python3-tk` apt package; `tests/test_ui.py` imports tkinter
too, so the suite needs it as well. `KAYTTOOHJE.md` still documents PowerShell and
Python 3.12 from the project's Windows origin — the code itself is
platform-agnostic stdlib.

**Standard library only.** No third-party dependencies, no venv, no build step, no
package manager. Do not introduce any.

## Architecture

Pure-logic modules have no Tkinter import; all UI lives in `ui.py`. Keep it that
way — it is what makes the logic testable without a display.

| Module | Responsibility |
|---|---|
| [mega_empires/data.py](mega_empires/data.py) | Immutable reference data: 18 civilizations, 51 Advances, credits, A.S.T. era boundaries, official scenario setups per player count |
| [mega_empires/models.py](mega_empires/models.py) | `GameState` / `PlayerState` dataclasses, JSON (de)serialisation, `normalize()` clamping |
| [mega_empires/scoring.py](mega_empires/scoring.py) | Score breakdown, ranking, tie-breaks, visible rank numbers |
| [mega_empires/ast_rules.py](mega_empires/ast_rules.py) | Basic A.S.T. era requirements, marker state (READY / BLOCKED / WARNING / FINISHED) |
| [mega_empires/credits.py](mega_empires/credits.py) | Colour credits, row-chain discounts, effective Advance purchase price |
| [mega_empires/sequence.py](mega_empires/sequence.py) | The 13 Sequence of Play phases and their computed player orders |
| [mega_empires/storage.py](mega_empires/storage.py) | Atomic JSON autosave to `tallennukset/nykyinen_peli.json` (gitignored) |
| [mega_empires/ui.py](mega_empires/ui.py) | Tkinter app: new-game wizard, three tabs (Scoreboard / A.S.T. / Sequence of Play), Advances and Details dialogs |

## Domain rules that are easy to get wrong

- **Scoring** (rulebook 13c): 1 VP per city; 1/3/6 VP per Advance by cost band
  (<100 / 100–200 / >200); 5 VP per A.S.T. step; optional +5 VP end-game bonus.
  Card VP is always derived from `data.py`, never typed in by the user.
- **A.S.T. bonus is conditional.** It is confirmed manually in the Details dialog
  during the final A.S.T. phase, never inferred from a Late Iron Age position.
  12+ players: at most two recipients, and they must be in different trade blocks.
- **Era boundaries are per civilization**, read from `AST_1–AST_3.jpg` into
  `BASIC_AST_ERA_STARTS`. Do not assume one shared table.
- **`ADVANCE_CHAINS` is derived positionally** — `data.py` slices `ADVANCES` into
  consecutive triples, so each row of `_ADVANCE_ROWS` is one 1 VP → 3 VP → 6 VP
  discount chain. **Reordering or inserting a row silently breaks the discount
  logic.** Append nothing to that tuple without re-checking the chains.
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
  cities 0–9, A.S.T. step 0–15, census 0–55, and dedupes advances.
- The save format is `version: 4`; `GameState.from_dict` migrates older saves.
  Bump the version and add a migration branch if the schema changes.
- Add tests to the matching `tests/test_*.py` for any logic change. UI tests
  construct objects via `object.__new__(MegaEmpiresApp)` and a bare `tk.Tcl()`
  interpreter to avoid opening a window — follow that pattern.
- Verify changes against 5-, 9-, 10-, and 18-player setups; those are the
  acceptance cases in `PROJEKTI.md` §10.

## Out of scope (do not build unasked)

Trade card hands or trading, automatic calamity resolution, map/token/ship
tracking, network multiplayer, accounts or cloud storage, hardening against
hand-edited save files, and games outside 5–18 players.
