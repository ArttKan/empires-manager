import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mega_empires.config import (
    CONFIG_PATH_VARIABLE,
    SERVER_VARIABLE,
    TOKEN_VARIABLE,
    config_path,
    load_server_config,
)


class ServerConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.path = Path(self._directory.name) / "config.json"
        self._environment = mock.patch.dict(
            os.environ, {CONFIG_PATH_VARIABLE: str(self.path)}
        )
        self._environment.start()
        for name in (SERVER_VARIABLE, TOKEN_VARIABLE):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self._environment.stop()
        self._directory.cleanup()

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_no_config_means_local(self) -> None:
        self.assertIsNone(load_server_config())

    def test_file_supplies_server_and_token(self) -> None:
        self._write({"server": "https://example.test", "token": "abc"})

        config = load_server_config()

        self.assertEqual(config.url, "https://example.test")
        self.assertEqual(config.token, "abc")

    def test_trailing_slash_is_trimmed(self) -> None:
        self._write({"server": "https://example.test/"})

        self.assertEqual(load_server_config().url, "https://example.test")

    def test_environment_overrides_the_file_per_field(self) -> None:
        self._write({"server": "https://file.test", "token": "file-token"})

        with mock.patch.dict(os.environ, {SERVER_VARIABLE: "https://env.test"}):
            config = load_server_config()

        self.assertEqual(config.url, "https://env.test")
        self.assertEqual(config.token, "file-token")

    def test_broken_config_falls_back_to_local_instead_of_crashing(self) -> None:
        self.path.write_text("{ not json", encoding="utf-8")

        self.assertIsNone(load_server_config())

    def test_config_path_follows_its_variable(self) -> None:
        self.assertEqual(config_path(), self.path)


if __name__ == "__main__":
    unittest.main()
