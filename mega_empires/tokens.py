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
* **elevated player** — puhelin, joka liittyi myös admin-koodilla. Varaa oman
  paikkansa tavalliseen tapaan, mutta saa muuttaa noita samoja kolmea kenttää
  kenen tahansa riviltä, ja ohittaa vaiheportit kuten kannettava. A.S.T. ja
  kierros pysyvät silti kannettavalla: korotus on pelinjohtajan apuväline
  naapurin rivin korjaamiseen, ei toinen täysi admin.

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
    # Korotettu pelaaja: oma paikka varattuna, mutta kirjoitusoikeus kaikkien
    # riveille. Ei tee tästä adminia — `is_admin` ratkaisee yhä A.S.T.:n,
    # kierroksen, uuden pelin ja aulan.
    elevated: bool = False

    @property
    def is_admin(self) -> bool:
        return self.kind == ADMIN

    @property
    def bypasses_gates(self) -> bool:
        """Saako vaiheportit ja korttien pysyvyyden ohittaa.

        Korotettu puhelin saa, koska korotuksen koko tarkoitus on korjata
        toisen rivi silloin kun se on väärin — ja väärin se huomataan yleensä
        vasta kun vaihe on jo vaihtunut.
        """

        return self.is_admin or self.elevated

    def may_command(self, civilization: str, command: str) -> bool:
        if self.is_admin:
            return True
        if command not in PLAYER_COMMANDS:
            return False
        return self.elevated or civilization == self.civilization


def tokens_path(directory: Path) -> Path:
    return directory / TOKENS_FILENAME


class TokenStore:
    """Sivilisaatiokohtaiset tokenit ja liittymisen tila."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self._data = data

    # -- luonti ja lataus ---------------------------------------------------

    @staticmethod
    def _code() -> str:
        return "".join(
            secrets.choice(_JOIN_ALPHABET) for _ in range(JOIN_CODE_LENGTH)
        )

    @classmethod
    def create(cls, civilizations, path: Path) -> "TokenStore":
        join_code = cls._code()
        admin_code = cls._code()
        # Kahden saman koodin osuminen on epätodennäköistä mutta ei mahdotonta,
        # ja silloin jokainen liittyjä olisi vahingossa korotettu.
        while admin_code == join_code:
            admin_code = cls._code()
        data = {
            "join_code": join_code,
            "admin_code": admin_code,
            "players": {
                name: {
                    "token": secrets.token_urlsafe(TOKEN_BYTES),
                    "claimed_at": None,
                    "elevated": False,
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

    @property
    def admin_code(self) -> str:
        return str(self._data.get("admin_code", ""))

    def code_kind(self, code: str) -> str:
        """Kumpi koodi annettiin: ADMIN, PLAYER, vai "" jos kumpikaan.

        Koodeja on kaksi mutta kenttä yksi: pöydässä sanotaan yksi merkkijono
        eikä selitetä mihin kahdesta kentästä se kuuluu. Korotus seuraa siitä
        kumman koodin liittyjä tiesi.
        """

        wanted = code.strip().upper()
        if not wanted:
            return ""
        if self.join_code and secrets.compare_digest(wanted, self.join_code):
            return PLAYER
        if self.admin_code and secrets.compare_digest(wanted, self.admin_code):
            return ADMIN
        return ""

    def is_elevated(self, civilization: str) -> bool:
        entry = self._data.get("players", {}).get(civilization)
        return bool(entry and entry.get("elevated"))

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
                return Principal(
                    PLAYER, name, elevated=bool(entry.get("elevated"))
                )
        return None

    # -- liittyminen ---------------------------------------------------------

    def claim(self, join_code: str, civilization: str, when: str) -> str:
        """Varaa sivilisaatio ja palauta sen token.

        Nostaa ValueErrorin jos koodi on väärä, sivilisaatiota ei ole tai se on
        jo varattu. Kertaalleen varattua ei voi napata toiselta ilman adminin
        vapautusta — se estää sen että kaksi pelaajaa päätyy samaan riviin.

        Kelpaa kumpi tahansa kahdesta koodista. Admin-koodilla varattu paikka
        merkitään korotetuksi; liittyminen itsessään menee samaa reittiä.
        """

        kind = self.code_kind(join_code)
        if not kind:
            raise ValueError("Wrong join code.")
        entry = self._data.get("players", {}).get(civilization)
        if entry is None:
            raise ValueError(f"{civilization} is not in this game.")
        if entry.get("claimed_at"):
            raise ValueError(f"{civilization} has already been claimed.")
        entry["claimed_at"] = when
        entry["elevated"] = kind == ADMIN
        self.save()
        return str(entry["token"])

    def release(self, civilization: str) -> None:
        """Vapauta varaus, esimerkiksi kun puhelin vaihtuu."""

        entry = self._data.get("players", {}).get(civilization)
        if entry is None:
            raise ValueError(f"{civilization} is not in this game.")
        entry["claimed_at"] = None
        # Vapautus on myös ainoa tapa perua korotus: paikka palaa täysin
        # tyhjäksi, ja seuraava liittyjä saa vain sen mitä koodillaan ansaitsee.
        entry["elevated"] = False
        self.save()
