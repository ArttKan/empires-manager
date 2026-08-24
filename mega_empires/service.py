"""Pelitilan komentorajapinta.

`GameService` on ainoa asia, joka saa muuttaa `GameState`-oliota. Käyttöliittymä
ja tuleva HTTP-kerros ovat molemmat sen asiakkaita eivätkä kosketa dataclasseja
suoraan.

Rajapinta on määritelty niin, että sen voi toteuttaa myös verkon yli:

* komennot ottavat **absoluuttisen arvon**, eivät muutosta. Kaksi rinnakkaista
  "+1" onnistuisi molemmat ja kaupunkeja tulisi kaksi lisää, vaikka käyttäjä näki
  vain yhden. Absoluuttinen arvo yhdessä `expected_version`-tarkistuksen kanssa
  hylkää vanhentuneen kirjoituksen sen sijaan, että se yliajaisi toisen muutoksen;
* komennot **palauttavat arvon eivätkä viittausta** sisäiseen tilaan. Verkon yli
  toimiva toteutus ei voi palauttaa elävää oliota, joten paikallinenkaan ei saa.

Moduuli on tarkoituksella pelkkää vakiokirjastoa: työpöytäsovelluksen on toimittava
ilman venviä ja FastAPIa.
"""

from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import GameState, PlayerState
from .storage import save_game


class CommandError(Exception):
    """Komentoa ei hyväksytty. HTTP-kerros kääntää alaluokat statuskoodeiksi."""


class UnknownPlayer(CommandError):
    """Sivilisaatiota ei ole tässä pelissä (HTTP 404)."""


class VersionConflict(CommandError):
    """Asiakkaan tuntema versio on vanhentunut (HTTP 409).

    Asiakkaan pitää hakea tuore tilannekuva ja yrittää uudelleen; komentoa ei
    saa yrittää uudelleen automaattisesti vanhalla arvolla.
    """

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"Expected version {expected} but the current version is {actual}."
        )
        self.expected = expected
        self.actual = actual


class RuleViolation(CommandError):
    """Komento rikkoisi pelisääntöä (HTTP 422)."""


class ServiceUnavailable(CommandError):
    """Palveluun ei saatu yhteyttä, tai sillä ei ole peliä (HTTP 503).

    Erotettu muista siksi, että käyttöliittymän on käyttäydyttävä eri tavalla:
    hylätty komento on käyttäjän virhe, katkennut yhteys ei ole. Jälkimmäisessä
    näkymä pidetään ennallaan eikä sitä tulkita pelitilan muutokseksi.
    """


@dataclass(frozen=True)
class CommandResult:
    """Komennon tulos. `player` on kopio, ei viittaus palvelun tilaan."""

    state_version: int
    player: PlayerState | None = None


class GameService(ABC):
    """Rajapinta, jonka sekä paikallinen että HTTP-toteutus toteuttavat."""

    @abstractmethod
    def snapshot(self) -> GameState:
        """Palauta koko pelitila kopiona."""

    @abstractmethod
    def set_cities(
        self,
        civilization: str,
        cities: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Aseta pelaajan kaupunkimäärä absoluuttisena arvona."""

    @abstractmethod
    def set_census(
        self,
        civilization: str,
        census: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Aseta pelaajan Census absoluuttisena arvona."""

    @abstractmethod
    def set_ast_bonus(
        self,
        civilization: str,
        granted: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Vahvista tai peru A.S.T.-loppubonus."""

    @abstractmethod
    def set_ast_step(
        self,
        civilization: str,
        ast_step: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Aseta pelaajan A.S.T.-askel absoluuttisena arvona."""

    @abstractmethod
    def set_advances(
        self,
        civilization: str,
        advances: list[str],
        flexible_credits: dict[str, int] | None = None,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Korvaa pelaajan Advance-kortit ja vapaat krediitit."""

    @abstractmethod
    def set_player_details(
        self,
        civilization: str,
        nickname: str,
        block: str,
        cities: int,
        ast_step: int,
        census: int,
        ast_bonus: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Aseta Details-dialogin kentät yhtenä atomisena komentona."""

    @abstractmethod
    def set_turn(
        self,
        round_number: int,
        current_phase: int,
        expected_state_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Aseta kierros ja vaihe. Pelitason komento, ei pelaajakohtainen."""


def validate_ast_bonus(
    game: GameState,
    civilization: str,
    granted: bool,
) -> None:
    """Tarkista skenaarion A.S.T.-bonussäännöt.

    Tämä oli aiemmin `PlayerDialog._save`-metodissa `ui.py`:ssä, jolloin sääntö
    ei koskenut mitään muuta asiakasta. Nostaminen tänne on koko Phase B:n idea
    pienoiskoossa: sääntö kuuluu ytimeen, ei yhteen dialogiin.

    Alle 12 pelaajan pelissä bonuksen voi saada vain yksi pelaaja. 12+ pelaajan
    yhdistelmäpelissä saajia voi olla enintään kaksi ja heidän on oltava eri
    kauppalohkoissa.
    """

    if not granted:
        return

    others = [
        player
        for player in game.players
        if player.civilization != civilization and player.ast_bonus
    ]
    if not others:
        return

    if game.player_count <= 11:
        raise RuleViolation(
            "The A.S.T. end-game bonus can be confirmed for only one player "
            "in this game."
        )
    if len(others) >= 2:
        raise RuleViolation(
            "The bonus can be confirmed for no more than two players in a "
            "combined game."
        )

    player = _find_player(game, civilization)
    if others[0].block == player.block:
        raise RuleViolation(
            "Two bonus recipients must belong to different trade blocks."
        )


def _find_player(game: GameState, civilization: str) -> PlayerState:
    for player in game.players:
        if player.civilization == civilization:
            return player
    raise UnknownPlayer(f"No player for civilization {civilization!r}.")


class LocalGameService(GameService):
    """Prosessin sisäinen toteutus, joka omistaa tilan ja kirjoittaa levylle.

    Työpöytäsovellus käyttää tätä suoraan; palvelimella HTTP-kerros kääriytyy
    tämän ympärille. Kirjoitukset sarjallistuvat, koska kirjoittavia prosesseja
    on tasan yksi.
    """

    def __init__(
        self,
        game: GameState,
        save_path: Path | None = None,
        log_path: Path | None = None,
    ) -> None:
        game.normalize()
        self._game = game
        self._save_path = save_path
        self._log_path = (
            log_path
            if log_path is not None
            else (save_path.with_suffix(".jsonl") if save_path else None)
        )

    # -- luku ---------------------------------------------------------------

    def snapshot(self) -> GameState:
        return copy.deepcopy(self._game)

    @property
    def state_version(self) -> int:
        return self._game.state_version

    def save(self) -> None:
        """Kirjoita tilannekuva levylle ilman komentoa.

        Tarvitaan kun peli otetaan käyttöön sellaisenaan (uusi peli), jolloin
        mitään komentoa ei ole suoritettu mutta tila on silti tallennettava.
        """

        self._save()

    # -- komennot -----------------------------------------------------------

    def set_cities(
        self,
        civilization: str,
        cities: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.cities = int(cities)
        return self._commit(
            player,
            "set_cities",
            {"civilization": civilization, "cities": player.cities},
            actor,
        )

    def set_census(
        self,
        civilization: str,
        census: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.census = int(census)
        return self._commit(
            player,
            "set_census",
            {"civilization": civilization, "census": player.census},
            actor,
        )

    def set_ast_bonus(
        self,
        civilization: str,
        granted: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        validate_ast_bonus(self._game, civilization, bool(granted))
        player.ast_bonus = bool(granted)
        return self._commit(
            player,
            "set_ast_bonus",
            {"civilization": civilization, "granted": player.ast_bonus},
            actor,
        )

    def set_ast_step(
        self,
        civilization: str,
        ast_step: int,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.ast_step = int(ast_step)
        return self._commit(
            player,
            "set_ast_step",
            {"civilization": civilization, "ast_step": player.ast_step},
            actor,
        )

    def set_advances(
        self,
        civilization: str,
        advances: list[str],
        flexible_credits: dict[str, int] | None = None,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        player = self._checked_player(civilization, expected_version)
        player.advances = list(advances)
        if flexible_credits is not None:
            player.flexible_credits = dict(flexible_credits)
        return self._commit(
            player,
            "set_advances",
            {
                "civilization": civilization,
                "advances": list(player.advances),
                "flexible_credits": dict(player.flexible_credits),
            },
            actor,
        )

    def set_player_details(
        self,
        civilization: str,
        nickname: str,
        block: str,
        cities: int,
        ast_step: int,
        census: int,
        ast_bonus: bool,
        expected_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        """Details-dialogi tallentaa kaikki kenttänsä kerralla.

        Yksi komento eikä kuutta: käyttäjän teko on yksi, joten myös
        versionnosto, lokirivi ja mahdollinen peruutus ovat yksi.
        """

        player = self._checked_player(civilization, expected_version)
        validate_ast_bonus(self._game, civilization, bool(ast_bonus))
        player.nickname = str(nickname)
        player.block = str(block)
        player.cities = int(cities)
        player.ast_step = int(ast_step)
        player.census = int(census)
        player.ast_bonus = bool(ast_bonus)
        return self._commit(
            player,
            "set_player_details",
            {
                "civilization": civilization,
                "nickname": player.nickname,
                "block": player.block,
                "cities": player.cities,
                "ast_step": player.ast_step,
                "census": player.census,
                "ast_bonus": player.ast_bonus,
            },
            actor,
        )

    def set_turn(
        self,
        round_number: int,
        current_phase: int,
        expected_state_version: int | None = None,
        actor: str = "",
    ) -> CommandResult:
        if (
            expected_state_version is not None
            and expected_state_version != self._game.state_version
        ):
            raise VersionConflict(
                expected_state_version, self._game.state_version
            )
        self._game.round_number = int(round_number)
        self._game.current_phase = int(current_phase)
        self._game.normalize()
        self._game.state_version += 1
        self._append_log(
            "set_turn",
            {
                "round_number": self._game.round_number,
                "current_phase": self._game.current_phase,
            },
            actor,
            None,
        )
        self._save()
        return CommandResult(state_version=self._game.state_version)

    # -- sisäiset ------------------------------------------------------------

    def _checked_player(
        self,
        civilization: str,
        expected_version: int | None,
    ) -> PlayerState:
        player = _find_player(self._game, civilization)
        if expected_version is not None and expected_version != player.version:
            raise VersionConflict(expected_version, player.version)
        return player

    def _commit(
        self,
        player: PlayerState,
        command: str,
        arguments: dict,
        actor: str,
    ) -> CommandResult:
        """Normalisoi, kasvata versiot, kirjaa loki ja tallenna tilannekuva.

        `normalize()` ajetaan vasta tässä, jotta rajojen ulkopuolinen arvo
        leikkautuu samalla tavalla riippumatta siitä mikä asiakas sen lähetti.
        """

        player.normalize()
        player.version += 1
        self._game.state_version += 1
        self._append_log(command, arguments, actor, player)
        self._save()
        return CommandResult(
            state_version=self._game.state_version,
            player=copy.deepcopy(player),
        )

    def _append_log(
        self,
        command: str,
        arguments: dict,
        actor: str,
        player: PlayerState | None,
    ) -> None:
        """Lisää rivi komentolokiin.

        Loki on lisäyksellinen: se antaa tarkastusjäljen ("kuka muutti mitä ja
        milloin"), joka on 16 kirjoittajan pelissä olennaisesti hyödyllisempi
        kuin yhden, ja pohjan yhden askeleen peruutukselle.
        """

        if self._log_path is None:
            return
        entry = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "actor": actor,
            "command": command,
            "arguments": arguments,
            "state_version": self._game.state_version,
            "player_version": player.version if player is not None else None,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _save(self) -> None:
        if self._save_path is None:
            return
        save_game(self._game, self._save_path)
