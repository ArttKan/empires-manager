# Deploying the Mega Empires backend

How to run the backend on your own Linux machine. Replace the placeholders
`<server>`, `<admin>`, `<domain>` and `<repo-url>` with your own.

## What this installs

A single uvicorn process serving the HTTP API and the players' web page. The
desktop app and the phones are its clients; the server is the only thing that
mutates game state.

| Path | Contents | Owner |
|---|---|---|
| `/home/megaempires/mega-empires-backend/` | git working tree | `megaempires` |
| `/home/megaempires/venv/` | virtualenv, deliberately outside the checkout | `megaempires` |
| `/var/lib/mega-empires/` | saved games and tokens, created by systemd | `megaempires` |
| `/etc/mega-empires-backend.env` | the server token | `root`, `0600` |

The venv and the game data live outside the checkout on purpose: `git pull`
replaces the working tree's tracked contents and must not be able to destroy the
Python environment or the saved games.

The service account name `megaempires` is written into the unit file and the
sudoers rule. If you change it, change it in both.

## Prerequisites

- Linux with systemd, and **Python 3.10 or newer**. Development happens on a
  newer version, but the code is kept 3.10-compatible.
- `python3-venv`
- Read access to the repository — a deploy key if it is private, see below
- A public address: Cloudflare Tunnel, Tailscale Funnel, or a reverse proxy
  terminating TLS. The service listens on `127.0.0.1:8000` only, so it is never
  directly exposed.

## Installation

### 1. Service account

```bash
sudo adduser --system --group --home /home/megaempires megaempires
```

This account has no sudo rights beyond the single rule added in step 4.

### 2. Deploy key (private repositories only)

```bash
sudo -u megaempires ssh-keygen -t ed25519 -C "mega-empires deploy" \
    -f /home/megaempires/.ssh/id_ed25519 -N ""
sudo -u megaempires cat /home/megaempires/.ssh/id_ed25519.pub
```

Add the public key under the repository's Deploy keys **without write access** —
the server only ever pulls. Verify with `sudo -u megaempires ssh -T git@github.com`.

### 3. Clone and virtualenv

```bash
sudo -u megaempires git clone <repo-url> /home/megaempires/mega-empires-backend
sudo -u megaempires python3 -m venv /home/megaempires/venv
sudo -u megaempires /home/megaempires/venv/bin/pip install --upgrade pip
sudo -u megaempires /home/megaempires/venv/bin/pip install -r \
    /home/megaempires/mega-empires-backend/requirements.txt
```

### 4. Token, unit and sudoers rule

The token is any random string; the desktop app uses the same one.

```bash
cd /home/megaempires/mega-empires-backend
sudo install -m 0600 -o root -g root /dev/null /etc/mega-empires-backend.env
printf 'ECHO_TOKEN=%s\n' "$(openssl rand -base64 24)" \
    | sudo tee /etc/mega-empires-backend.env >/dev/null

sudo cp deploy/mega-empires-backend.service /etc/systemd/system/
sudo install -m 0440 -o root -g root \
    deploy/megaempires-deploy.sudoers /etc/sudoers.d/megaempires-deploy
sudo visudo -c
sudo systemctl daemon-reload
sudo systemctl enable --now mega-empires-backend.service
```

Create the env file **before** the first start: `EnvironmentFile` is deliberately
mandatory, so a missing file stops the service rather than letting it run
without a token.

The variable name `ECHO_TOKEN` is historical. `main.py` also accepts
`MEGA_EMPIRES_TOKEN` if you would rather rename it.

The sudoers rule grants the service account exactly one privilege: restarting
this one service. `deploy.sh` needs it; nothing else is permitted.

### 5. Public exposure

The service listens on `127.0.0.1:8000`. Point `<domain>` at it however you
prefer. Cloudflare Tunnel suits a home machine: no inbound ports, no public IP
required, and TLS handled for you.

Two things to expect behind a tunnel or proxy:

- **The `/events` SSE stream needs a heartbeat.** The app sends one every 15
  seconds, because proxies reap idle connections.
- **Cloudflare rejects urllib's default User-Agent** with error 1010. The desktop
  app sends its own identifier, so this is already handled — do not remove it.

### 6. Verification

```bash
systemctl status mega-empires-backend.service
ls -ld /var/lib/mega-empires
curl -s http://127.0.0.1:8000/health
curl -s https://<domain>/health
```

Finish on a phone using mobile data with wifi off. That is the real path, and
the local network tells you nothing about it.

## Updating

From the development machine:

```bash
git push origin main
```

On the server:

```bash
ssh <admin>@<server>
sudo -u megaempires /home/megaempires/mega-empires-backend/deploy/deploy.sh
```

The script fetches, reinstalls dependencies only when `requirements.txt` changed,
**runs the tests, and restarts only if they pass**. A broken push therefore
cannot take the running service down.

`tests/test_ui.py` skips itself because the server has no `python3-tk`. Seeing
`skipped=1` is expected, not a problem.

Defaults can be overridden with environment variables:

```bash
BRANCH=some-branch APP_DIR=/other/path sudo -u megaempires .../deploy.sh
```

### The unit file does not update with a deploy

The service account may restart the service but not write to
`/etc/systemd/system/`. A change to the unit file therefore lands in the
repository without taking effect. `deploy.sh` warns about this at the end of a
run; install the change with an admin account:

```bash
sudo cp /home/megaempires/mega-empires-backend/deploy/mega-empires-backend.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mega-empires-backend.service
```

## The unit file and secrets

The unit contains no secrets, so it is an ordinary tracked file and the
repository's copy is the only copy. The token is read separately:

```ini
EnvironmentFile=/etc/mega-empires-backend.env
```

That file is `root:root 0600`. systemd reads it before dropping to the
`megaempires` user, so the service account never needs access to it at all.

**Do not put the token back into the unit.** It was done that way once and hidden
with `git update-index --skip-worktree`; the side effect was that unit changes
never reached the server and nothing said so.

### Changing the token

```bash
printf 'ECHO_TOKEN=%s\n' '<new token>' | sudo tee /etc/mega-empires-backend.env >/dev/null
sudo systemctl restart mega-empires-backend.service
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/state \
  -H "Authorization: Bearer <new token>"
```

200 means the token reached the process; 401 means it differs from the one you
sent. Remember to update the desktop machine's `~/.config/mega-empires/config.json`
as well.

## Creating a game

Games are created with the desktop app's wizard in remote mode, which posts a
complete game state to `POST /game`. Nothing needs copying to the server by hand,
and no restart is required.

The server holds exactly one game, at `/var/lib/mega-empires/nykyinen_peli.json`.
Installing a new one **archives the previous game** under a timestamped name,
along with its command log, so a mistaken click cannot destroy a game in
progress. Archives are never pruned automatically; they are a few kilobytes each.

`GET /state` answers **503** when there is no game. That is information, not a
fault.

If you replace the game file on disk by hand, restart the service: it reads the
save once and keeps it in memory.

## Checking the routes

```bash
TOKEN=<token>
curl -s https://<domain>/health
curl -s https://<domain>/state -H "Authorization: Bearer $TOKEN"
curl -s -X POST https://<domain>/players/Minoa/cities \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"value": 4}'
```

Expected error codes: 401 unknown token, 403 known but not permitted, 404 unknown
civilization, 409 stale `expected_version` (the response carries the current one),
422 rule or phase violation.

The SSE stream needs no token, because it carries no game data — only a version
number:

```bash
curl -N https://<domain>/events
```

## Why a restart can hang

`/events` is an infinite response, and uvicorn waits for in-flight requests to
finish before exiting. A single open phone or `curl -N` keeps the process alive
until systemd kills it after `TimeoutStopSec` (90 seconds by default).

**This cannot be fixed in the application.** uvicorn runs lifespan shutdown
*after* draining requests, so a handler that would close the streams is itself
waiting on those streams. The fix belongs in the unit:

```ini
ExecStart=… --timeout-graceful-shutdown 5
TimeoutStopSec=20
```

With those, shutdown takes about five seconds even with open streams.

## Troubleshooting

```bash
journalctl -u mega-empires-backend.service -n 50 --no-pager
systemctl cat mega-empires-backend.service
curl -s http://127.0.0.1:8000/health
```

- **Service will not start:** does `/etc/mega-empires-backend.env` exist? A
  missing `EnvironmentFile` stops startup by design.
- **Git complains about directory ownership:** the command is running as the
  wrong user — check `sudo -u megaempires`.
- **A change does not appear even though the deploy succeeded:** if the change
  was in the unit file, it has to be installed separately (see above).

## Backups

`/var/lib/mega-empires/` holds the games, the command logs and the player tokens.
It is kilobytes, so a nightly rsync is plenty. **`/etc/mega-empires-backend.env`
is a secret** and does not belong in the same backup as the game data.
