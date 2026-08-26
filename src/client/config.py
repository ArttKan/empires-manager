"""Palvelinasetusten lukeminen.

Työpöytäsovellus ajetaan normaalisti palvelinta vasten, joten osoitetta ja
tokenia ei haluta kirjoittaa käynnistysriville joka kerta. Asetukset luetaan
tiedostosta, jonka ympäristömuuttujat voivat ohittaa.

Ratkaisu tehdään kutsuhetkellä eikä tuontihetkellä, samasta syystä kuin
`storage.data_directory()`: testit ja käynnistysympäristö voivat asettaa
muuttujat prosessin käynnistyksen jälkeen.

Vain vakiokirjastoa — tämä on työpöytäsovelluksen polulla.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

SERVER_VARIABLE = "MEGA_EMPIRES_SERVER"
TOKEN_VARIABLE = "MEGA_EMPIRES_TOKEN"
CONFIG_PATH_VARIABLE = "MEGA_EMPIRES_CONFIG"

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "mega-empires" / "config.json"


@dataclass(frozen=True, slots=True)
class ServerConfig:
    url: str
    token: str


def config_path() -> Path:
    configured = os.environ.get(CONFIG_PATH_VARIABLE, "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH


def _file_values() -> dict:
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Puuttuva tai rikkinäinen asetustiedosto ei saa estää käynnistystä:
        # sovellus putoaa silloin paikalliseen tilaan.
        return {}
    return data if isinstance(data, dict) else {}


def load_server_config() -> ServerConfig | None:
    """Palauta palvelinasetukset tai None, jos peli ajetaan paikallisesti.

    Ympäristömuuttuja voittaa tiedoston kenttäkohtaisesti, jotta esimerkiksi
    pelkän osoitteen voi vaihtaa hetkeksi ilman että token pitää toistaa.
    """

    values = _file_values()
    url = (
        os.environ.get(SERVER_VARIABLE, "").strip()
        or str(values.get("server", "")).strip()
    )
    if not url:
        return None
    token = (
        os.environ.get(TOKEN_VARIABLE, "").strip()
        or str(values.get("token", "")).strip()
    )
    return ServerConfig(url=url.rstrip("/"), token=token)
