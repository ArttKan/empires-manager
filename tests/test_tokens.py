import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from src.server.tokens import (
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


class ElevatedPlayerTests(unittest.TestCase):
    """Korotettu pelaaja: oma paikka, mutta kirjoitusoikeus kaikkien riveille."""

    def test_elevated_player_may_edit_any_row(self) -> None:
        elevated = Principal(PLAYER, "Hellas", elevated=True)

        for civilization in ("Hellas", "Minoa", "Saba"):
            for command in PLAYER_COMMANDS:
                self.assertTrue(
                    elevated.may_command(civilization, command),
                    f"{command} for {civilization}",
                )

    def test_elevation_widens_the_rows_not_the_commands(self) -> None:
        """A.S.T. ja kierros jäävät kannettavalle myös korotetulta."""

        elevated = Principal(PLAYER, "Hellas", elevated=True)

        self.assertFalse(elevated.is_admin)
        for command in ("ast-step", "ast-bonus", "details", "turn", "game"):
            self.assertFalse(elevated.may_command("Hellas", command))
            self.assertFalse(elevated.may_command("Minoa", command))

    def test_only_admin_and_elevated_bypass_the_gates(self) -> None:
        self.assertTrue(Principal(ADMIN).bypasses_gates)
        self.assertTrue(Principal(PLAYER, "Hellas", elevated=True).bypasses_gates)
        self.assertFalse(Principal(PLAYER, "Hellas").bypasses_gates)


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

    def _wrong_admin_code(self) -> str:
        """Varmasti väärä koodi — arvattu merkkijono voisi osua oikeaan."""

        return "".join("A" if c != "A" else "B" for c in self.store.admin_code)

    def test_admin_code_is_a_second_distinct_code(self) -> None:
        self.assertTrue(self.store.admin_code)
        self.assertNotEqual(self.store.admin_code, self.store.join_code)

    def test_a_plain_claim_is_not_elevated(self) -> None:
        self.store.claim(self.store.join_code, "Hellas", "now")

        self.assertTrue(self.store.is_claimed("Hellas"))
        self.assertFalse(self.store.is_elevated("Hellas"))

    def test_claiming_with_the_admin_code_elevates(self) -> None:
        token = self.store.claim(self.store.admin_code, "Hellas", "now")

        self.assertTrue(self.store.is_elevated("Hellas"))
        principal = self.store.principal_for(token, ADMIN_TOKEN)
        self.assertTrue(principal.elevated)
        # Korotus ei ole adminius: se ratkaisee yhä A.S.T.:n ja aulan.
        self.assertFalse(principal.is_admin)
        self.assertEqual(principal.civilization, "Hellas")

    def test_code_kind_tells_the_two_codes_apart(self) -> None:
        """Kenttiä on yksi, joten koodi itse ratkaisee mitä siitä seuraa."""

        self.assertEqual(self.store.code_kind(self.store.join_code), PLAYER)
        self.assertEqual(self.store.code_kind(self.store.admin_code), ADMIN)
        self.assertEqual(self.store.code_kind(self._wrong_admin_code()), "")
        self.assertEqual(self.store.code_kind(""), "")

    def test_code_kind_trims_and_ignores_case(self) -> None:
        """Koodi sanotaan ääneen ja näppäillään puhelimella."""

        self.assertEqual(
            self.store.code_kind("  " + self.store.admin_code.lower() + "  "),
            ADMIN,
        )

    def test_release_also_cancels_the_elevation(self) -> None:
        """Vapautus on ainoa peruutustapa, joten sen on siivottava kaikki."""

        self.store.claim(self.store.admin_code, "Hellas", "now")
        self.store.release("Hellas")

        self.assertFalse(self.store.is_elevated("Hellas"))
        self.store.claim(self.store.join_code, "Hellas", "later")
        self.assertFalse(self.store.is_elevated("Hellas"))

    def test_a_store_from_before_this_feature_still_works(self) -> None:
        """Kesken pelin päivitetty palvelin: vanhassa tiedostossa ei ole koodia.

        Tavallisen liittymisen on toimittava, ja korotuksen on kieltäydyttävä
        sen sijaan että tyhjä koodi kelpaisi mihin tahansa syötteeseen.
        """

        data = json.loads(self.path.read_text(encoding="utf-8"))
        del data["admin_code"]
        for entry in data["players"].values():
            entry.pop("elevated", None)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        store = TokenStore.load(self.path)

        self.assertEqual(store.admin_code, "")
        self.assertTrue(store.claim(store.join_code, "Minoa", "now"))
        self.assertFalse(store.is_elevated("Minoa"))

        # Tyhjä koodi ei saa vastata mihinkään syötteeseen — muuten jokainen
        # liittyisi korotettuna palvelimella jota ei ole vielä käynnistetty
        # uudella pelillä.
        self.assertEqual(store.code_kind(""), "")
        self.assertEqual(store.code_kind("ABCDE"), "")
        self.assertFalse(store.is_claimed("Hellas"))

    def test_elevation_survives_a_reload(self) -> None:
        self.store.claim(self.store.admin_code, "Hellas", "now")

        reloaded = TokenStore.load(self.path)

        self.assertEqual(reloaded.admin_code, self.store.admin_code)
        self.assertTrue(reloaded.is_elevated("Hellas"))
        self.assertFalse(reloaded.is_elevated("Minoa"))

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
