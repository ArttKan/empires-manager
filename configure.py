"""Kirjoita palvelinasetukset työpöytäsovellusta varten.

Käyttö:
    python configure.py                              kysyy arvot
    python configure.py --server URL --token TOKEN   suoraan, ilman kysymyksiä
    python configure.py --local                      poistaa asetukset

Tarkoitettu jaettavaksi peliporukalle, erityisesti Windowsissa, jossa
asetustiedoston polku (`%USERPROFILE%\\.config\\mega-empires\\config.json`) on
epätavallinen eikä kukaan arvaisi sitä.

Skripti käyttää sovelluksen omaa `config`-moduulia, joten polku ei voi erkaantua
siitä mitä sovellus tosiasiassa lukee. Vain vakiokirjastoa: tämä ajetaan samalla
Pythonilla kuin sovelluskin, ilman venviä.

Aja: python configure.py
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mega_empires.config import config_path, load_server_config  # noqa: E402


def _mask(secret: str) -> str:
    """Näytä sen verran että arvon tunnistaa, ei enempää."""

    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"


def _ask(prompt: str, current: str, secret: bool = False) -> str:
    """Kysy arvo. Token näkyy kirjoitettaessa.

    Aiemmin käytettiin `getpass`ia, mutta se lukee merkkejä yksitellen
    `msvcrt`:llä eikä liittäminen toimi PowerShellissä. Tokenin piilottaminen ei
    ole sen arvoista että arvoa ei saa liitettyä: käyttäjä asettaa sitä omalle
    koneelleen ja on juuri saanut sen jostain mistä sen näkee muutenkin.
    """

    shown = _mask(current) if secret and current else current
    suffix = f" [{shown}]" if current else ""
    return input(f"{prompt}{suffix}: ").strip() or current


def _check(url: str, token: str) -> None:
    """Kokeile yhteyttä samalla asiakkaalla jota sovellus käyttää.

    Näin väärä token huomataan heti eikä vasta pelipöydässä.
    """

    from mega_empires.remote import RemoteGameService
    from mega_empires.service import CommandError

    service = RemoteGameService(url, token, timeout=8.0)
    try:
        game = service.snapshot()
    except CommandError as error:
        message = str(error)
        if "Invalid bearer token" in message or "Authentication" in message:
            print("\n  The server answered, but rejected the token.")
            print("  Check it against the server's env file.")
        elif "No saved game" in message:
            print("\n  Connected. The server has no game yet — that is fine;")
            print("  create one from the app's New Game wizard.")
        else:
            print(f"\n  Could not reach the server: {message}")
        return
    print(f"\n  Connected. Current game: {game.player_count} players, "
          f"turn {game.round_number}.")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write the Mega Empires server settings for the desktop app."
    )
    parser.add_argument("--server", help="server address, e.g. https://your.domain")
    parser.add_argument("--token", help="the server's token")
    parser.add_argument(
        "--local",
        action="store_true",
        help="remove the settings and play local games",
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="skip the connection check",
    )
    return parser.parse_args()


def main() -> int:
    options = _arguments()
    path = config_path()
    existing = load_server_config()

    if options.local:
        if path.is_file():
            path.unlink()
            print(f"Removed {path}. The app will open local games.")
        else:
            print("Nothing to remove.")
        return 0

    # Suoraan annetut arvot ohittavat kysymykset, jotta ohjeen voi lähettää
    # yhtenä valmiina komentona.
    if options.server and options.token:
        return _write(path, options.server, options.token, not options.no_test)

    print("Mega Empires — server settings\n")
    print(f"  Config file: {path}")
    if existing:
        print(f"  Currently:   {existing.url}  (token {_mask(existing.token)})")
    else:
        print("  Currently:   not configured — the app opens local games")
    print("\nPress Enter to keep a value shown in brackets.")
    print('Type "local" as the server to remove the settings and play offline.\n')

    url = _ask("Server address", existing.url if existing else "")
    # Tyhjä syöte säilyttää nykyisen arvon, joten poistolle tarvitaan oma sana.
    if url.lower() in {"local", "none", "-"}:
        if path.is_file():
            path.unlink()
            print(f"\n  Removed {path}. The app will open local games.")
        else:
            print("\n  Nothing to remove.")
        return 0
    if not url:
        print("\n  No server given. Nothing was written.")
        return 0
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        print(f"  Assuming https: {url}")

    token = _ask("Token", existing.token if existing else "", secret=True)
    if not token:
        print("\n  A token is required. Nothing was written.", file=sys.stderr)
        return 1

    test = input("\nTest the connection now? [Y/n]: ").strip().lower() not in {"n", "no"}
    return _write(path, url, token, test)


def _write(path: Path, url: str, token: str, test: bool) -> int:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"server": url.rstrip("/"), "token": token}, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        # Vaikuttaa vain POSIXissa; Windowsissa tiedosto perii kotihakemiston
        # oikeudet, mikä on käytännössä sama asia yhden käyttäjän koneella.
        path.chmod(0o600)
    except OSError:
        pass

    written = load_server_config()
    if written is None or written.token != token:
        print("\n  The file was written but does not read back correctly.",
              file=sys.stderr)
        return 1
    print(f"\n  Saved to {path}")

    if test:
        _check(url, token)

    print("\nDone. Start the app with:  python app.py")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        code = 1
    # Windowsissa skriptin voi käynnistää kaksoisnapsautuksella, jolloin ikkuna
    # sulkeutuisi heti eikä tulostetta ehtisi lukea.
    if os.name == "nt":
        input("\nPress Enter to close.")
    sys.exit(code)
