"""Pelaajakohtaiset tokenit ja niiden liittymisvirta.

Tokenit pidetään erillään `GameState`:sta tarkoituksella. Pelitila
serialisoidaan tallennuksiin, komentolokin viereen ja kannettavan peilikopioon;
jos tokenit olisivat siinä, jokaisen pelaajan salaisuus vuotaisi kaikkiin noihin
paikkoihin. Tämä tiedosto on vain palvelimella.

Oikeusmalli on tahallaan karkea, koska peliporukka on pieni ja tuttu:

* **admin** — kannettava. Saa tehdä kaiken.
* **player** — puhelin. Saa muuttaa vain oman sivilisaationsa kaupunkeja,
  Censusta ja Advance-kortteja. A.S.T.-askel, bonus, kierros ja uusi peli ovat
  vain adminille.

Vain vakiokirjastoa.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

# Liittymiskoodi luetaan ääneen pöydässä, joten siitä jätetään pois merkit jotka
# sekoittuvat puheessa tai näytöllä (0/O, 1/I/L).
_JOIN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 5
TOKEN_BYTES = 16

TOKENS_FILENAME = "tokens.json"

ADMIN = "admin"
PLAYER = "player"

# Reitit, joita puhelin saa kutsua. A.S.T.-askel puuttuu tästä tarkoituksella:
# se on pelin lopputuloksen kannalta ratkaiseva ja jää kannettavalle.
PLAYER_COMMANDS = frozenset({"cities", "census", "advances"})


@dataclass(frozen=True, slots=True)
class Principal:
    kind: str
    civilization: str = ""

    @property
    def is_admin(self) -> bool:
        return self.kind == ADMIN

    def may_command(self, civilization: str, command: str) -> bool:
        if self.is_admin:
            return True
        return (
            civilization == self.civilization
            and command in PLAYER_COMMANDS
        )


def tokens_path(directory: Path) -> Path:
    return directory / TOKENS_FILENAME


class TokenStore:
    """Sivilisaatiokohtaiset tokenit ja liittymisen tila."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self._data = data

    # -- luonti ja lataus ---------------------------------------------------

    @classmethod
    def create(cls, civilizations, path: Path) -> "TokenStore":
        data = {
            "join_code": "".join(
                secrets.choice(_JOIN_ALPHABET) for _ in range(JOIN_CODE_LENGTH)
            ),
            "players": {
                name: {
                    "token": secrets.token_urlsafe(TOKEN_BYTES),
                    "claimed_at": None,
                }
                for name in civilizations
            },
        }
        store = cls(path, data)
        store.save()
        return store

    @classmethod
    def load(cls, path: Path) -> "TokenStore | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or "players" not in data:
            return None
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Tokenit ovat salaisuuksia: vain omistaja saa lukea.
        temporary.chmod(0o600)
        temporary.replace(self.path)

    # -- kyselyt ------------------------------------------------------------

    @property
    def join_code(self) -> str:
        return str(self._data.get("join_code", ""))

    def civilizations(self) -> tuple:
        return tuple(self._data.get("players", {}))

    def is_claimed(self, civilization: str) -> bool:
        entry = self._data.get("players", {}).get(civilization)
        return bool(entry and entry.get("claimed_at"))

    def status(self) -> tuple:
        """(sivilisaatio, varattu) jokaisesta pelaajasta, järjestyksessä."""

        return tuple(
            (name, self.is_claimed(name)) for name in self.civilizations()
        )

    def principal_for(self, token: str, admin_token: str) -> Principal | None:
        """Tunnista token. Palauta None jos se ei kelpaa.

        Vertailu tehdään `compare_digest`illä, jotta vastausaika ei paljasta
        kuinka pitkälle token osui oikein.
        """

        if not token:
            return None
        if admin_token and secrets.compare_digest(token, admin_token):
            return Principal(ADMIN)
        for name, entry in self._data.get("players", {}).items():
            stored = str(entry.get("token", ""))
            if stored and secrets.compare_digest(token, stored):
                return Principal(PLAYER, name)
        return None

    # -- liittyminen ---------------------------------------------------------

    def claim(self, join_code: str, civilization: str, when: str) -> str:
        """Varaa sivilisaatio ja palauta sen token.

        Nostaa ValueErrorin jos koodi on väärä, sivilisaatiota ei ole tai se on
        jo varattu. Kertaalleen varattua ei voi napata toiselta ilman adminin
        vapautusta — se estää sen että kaksi pelaajaa päätyy samaan riviin.
        """

        if not self.join_code or not secrets.compare_digest(
            join_code.strip().upper(), self.join_code
        ):
            raise ValueError("Wrong join code.")
        entry = self._data.get("players", {}).get(civilization)
        if entry is None:
            raise ValueError(f"{civilization} is not in this game.")
        if entry.get("claimed_at"):
            raise ValueError(f"{civilization} has already been claimed.")
        entry["claimed_at"] = when
        self.save()
        return str(entry["token"])

    def release(self, civilization: str) -> None:
        """Vapauta varaus, esimerkiksi kun puhelin vaihtuu."""

        entry = self._data.get("players", {}).get(civilization)
        if entry is None:
            raise ValueError(f"{civilization} is not in this game.")
        entry["claimed_at"] = None
        self.save()
