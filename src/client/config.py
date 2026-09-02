"""Reading the server settings.

The desktop app normally runs against a server, so nobody wants to type the
address and token on the command line every time. The settings are read from a
file, which environment variables may override.

Resolution happens at call time rather than import time, for the same reason as
`storage.data_directory()`: tests and the launch environment may set the
variables after the process has started.

Standard library only — this is on the desktop app's path.
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
        # A missing or broken config file must not block startup: the app falls back
        # to local mode instead.
        return {}
    return data if isinstance(data, dict) else {}


def load_server_config() -> ServerConfig | None:
    """Return the server settings, or None if the game runs locally.

    An environment variable beats the file per field, so that for instance the
    address alone can be changed for a moment without repeating the token.
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
