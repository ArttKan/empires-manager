import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from mega_empires.tokens import (
    ADMIN,
    PLAYER,
    PLAYER_COMMANDS,
    Principal,
    TokenStore,
    tokens_path,
)

CIVS = ("Minoa", "Saba", "Hellas")
ADMIN_TOKEN = "admin-secret"


class PermissionTests(unittest.TestCase):
    def test_admin_may_do_anything(self) -> None:
        admin = Principal(ADMIN)

        for command in ("cities", "census", "advances", "ast-step", "details"):
            self.assertTrue(admin.may_command("Hellas", command))

    def test_player_may_only_touch_their_own_row(self) -> None:
        player = Principal(PLAYER, "Hellas")

        self.assertTrue(player.may_command("Hellas", "cities"))
        self.assertFalse(player.may_command("Minoa", "cities"))

    def test_player_may_use_exactly_the_three_agreed_commands(self) -> None:
        player = Principal(PLAYER, "Hellas")

        self.assertEqual(PLAYER_COMMANDS, {"cities", "census", "advances"})
        for command in PLAYER_COMMANDS:
            self.assertTrue(player.may_command("Hellas", command))

    def test_ast_step_is_never_available_to_a_player(self) -> None:
        """A.S.T.-askel on pelin ratkaiseva tieto ja jää kannettavalle."""

        player = Principal(PLAYER, "Hellas")

        for command in ("ast-step", "ast-bonus", "details", "turn", "game"):
            self.assertFalse(player.may_command("Hellas", command))


class TokenStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.path = tokens_path(Path(self._directory.name))
        self.store = TokenStore.create(CIVS, self.path)

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_every_civilization_gets_a_distinct_token(self) -> None:
        tokens = {
            civ: json.loads(self.path.read_text())["players"][civ]["token"]
            for civ in CIVS
        }

        self.assertEqual(len(set(tokens.values())), len(CIVS))
        for token in tokens.values():
            self.assertGreaterEqual(len(token), 20)

    def test_join_code_avoids_ambiguous_characters(self) -> None:
        """Koodi luetaan ääneen, joten 0/O ja 1/I/L jätetään pois."""

        self.assertTrue(self.store.join_code)
        for character in self.store.join_code:
            self.assertNotIn(character, "01OIL")

    def test_token_file_is_owner_only(self) -> None:
        mode = stat.S_IMODE(os.stat(self.path).st_mode)

        self.assertEqual(mode, 0o600)

    def test_admin_token_resolves_to_admin(self) -> None:
        principal = self.store.principal_for(ADMIN_TOKEN, ADMIN_TOKEN)

        self.assertTrue(principal.is_admin)

    def test_player_token_resolves_to_its_civilization(self) -> None:
        token = self.store.claim(self.store.join_code, "Saba", "now")

        principal = self.store.principal_for(token, ADMIN_TOKEN)

        self.assertEqual(principal.kind, PLAYER)
        self.assertEqual(principal.civilization, "Saba")

    def test_unknown_token_resolves_to_nothing(self) -> None:
        self.assertIsNone(self.store.principal_for("nope", ADMIN_TOKEN))
        self.assertIsNone(self.store.principal_for("", ADMIN_TOKEN))

    def test_claim_requires_the_right_code(self) -> None:
        with self.assertRaises(ValueError):
            self.store.claim("WRONG", "Saba", "now")

        self.assertFalse(self.store.is_claimed("Saba"))

    def test_claim_is_case_insensitive_and_trims(self) -> None:
        code = self.store.join_code.lower()

        self.store.claim(f"  {code} ", "Saba", "now")

        self.assertTrue(self.store.is_claimed("Saba"))

    def test_a_seat_cannot_be_taken_twice(self) -> None:
        self.store.claim(self.store.join_code, "Saba", "now")

        with self.assertRaises(ValueError):
            self.store.claim(self.store.join_code, "Saba", "later")

    def test_unknown_civilization_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.claim(self.store.join_code, "Atlantis", "now")

    def test_release_frees_the_seat_again(self) -> None:
        """Puhelimen vaihto tai selaimen tyhjennys ei saa lukita pelaajaa ulos."""

        first = self.store.claim(self.store.join_code, "Saba", "now")
        self.store.release("Saba")

        second = self.store.claim(self.store.join_code, "Saba", "later")

        self.assertTrue(self.store.is_claimed("Saba"))
        self.assertEqual(first, second)

    def test_status_reports_who_has_joined(self) -> None:
        self.store.claim(self.store.join_code, "Saba", "now")

        self.assertEqual(
            self.store.status(),
            (("Minoa", False), ("Saba", True), ("Hellas", False)),
        )

    def test_store_survives_a_reload(self) -> None:
        token = self.store.claim(self.store.join_code, "Saba", "now")

        reloaded = TokenStore.load(self.path)

        self.assertEqual(reloaded.join_code, self.store.join_code)
        self.assertTrue(reloaded.is_claimed("Saba"))
        self.assertEqual(
            reloaded.principal_for(token, ADMIN_TOKEN).civilization, "Saba"
        )

    def test_missing_or_broken_file_loads_as_nothing(self) -> None:
        self.assertIsNone(TokenStore.load(Path("/nonexistent/tokens.json")))
        self.path.write_text("{ not json", encoding="utf-8")
        self.assertIsNone(TokenStore.load(self.path))


if __name__ == "__main__":
    unittest.main()
