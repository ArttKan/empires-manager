import tkinter as tk
import unittest

from mega_empires.models import PlayerState
from mega_empires.ui import MegaEmpiresApp


class ScoreboardUiTests(unittest.TestCase):
    def test_census_entry_commits_directly_without_refresh(self) -> None:
        interpreter = tk.Tcl()
        value = tk.StringVar(master=interpreter, value="37")
        player = PlayerState("Minoa", "Mia", "WEST", census=12)
        app = object.__new__(MegaEmpiresApp)
        save_calls: list[bool] = []
        app._save = lambda: save_calls.append(True)

        app._commit_census(player, value)

        self.assertEqual(player.census, 37)
        self.assertEqual(len(save_calls), 1)

        app._commit_census(player, value)
        self.assertEqual(len(save_calls), 1)


if __name__ == "__main__":
    unittest.main()
