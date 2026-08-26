# Mega Empires score tracker

A desktop app for keeping score in a game of the **Mega Empires** board game
(The West and/or The East), for 3–18 players. It tracks cities, the Archeological
Succession Table, Census and Civilization Advances, works out the scores and
player orders from the rules, and shows all eighteen players on one screen — the
laptop drives a TV so everyone at the table can see the standings.

It optionally runs against a small self-hosted backend, so players can enter their
own cities, Census and Advances from their phones. See
[deploy/README.md](deploy/README.md) for that side; the desktop app works fine
without it.

Built for one gaming group rather than for general use, so it favours being quick
to use mid-game over being defensive about input.

## Running the desktop app

Needs **Python 3.10 or newer** and tkinter. Nothing else — the desktop app is
standard library only, with no virtualenv and no install step.

```bash
sudo apt install python3-tk        # Debian/Ubuntu; other distros vary
python3 app.py
```

Saved games are written to `tallennukset/` beside the code, or to whatever
`MEGA_EMPIRES_DATA_DIR` points at. Every change is saved immediately.

## Playing against a server

If `~/.config/mega-empires/config.json` exists, the app connects to that server
instead of opening a local save:

```json
{
  "server": "https://your.domain",
  "token": "the server's token"
}
```

The game then lives on the server and phones can join it. If the server cannot be
reached, the app offers to continue offline from its local mirror of the last
state it saw.

Without that file, everything stays local — which is also what makes a fresh
checkout and the test suite work with no setup.

## Tests

```bash
python3 -m unittest discover
```

The HTTP and remote-service tests need the server dependencies from
`requirements.txt` and skip themselves when those are missing, so a green run
under bare `python3` covers the game logic and the desktop app only.
