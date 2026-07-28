"""Tkinter-käyttöliittymä Mega Empires -peliseurannalle."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from typing import Callable

from .ast_rules import BASIC_AST_REQUIREMENTS, ast_marker_state
from .data import (
    ADVANCES,
    ADVANCE_BY_ID,
    ADVANCE_GROUPS,
    Advance,
    AST_ERA_ABBREVIATIONS,
    AST_ERA_NAMES,
    AST_MAX_STEP,
    CIVILIZATION_BY_NAME,
    GAME_MODE_LABELS,
    ast_era_index,
    basic_ast_era_starts,
    default_block,
    scenario_civilizations,
)
from .credits import advance_price, color_credits, flexible_credit_entitlement
from .models import GameState, PlayerState
from .scoring import calculate_score, players_in_ast_order, visible_rankings
from .sequence import (
    PHASES,
    PHASE_BY_NUMBER,
    SPECIAL_ABILITY_ADVANCES,
    Phase,
    adjacent_phase,
    phase_order,
)
from .storage import (
    SavedGame,
    list_saved_games,
    load_game,
    save_game,
    save_path_for_name,
)


BACKGROUND = "#101722"
PANEL = "#182231"
PANEL_ALT = "#223044"
TEXT = "#f5f7fa"
MUTED = "#aeb9c7"
ACCENT = "#d6a642"
ERROR = "#b94141"
AST_ERA_COLORS = (
    "#354252",
    "#51463f",
    "#555444",
    "#44546a",
    "#685a34",
    "#6b4039",
)
AST_MARKER_STYLES = {
    "READY": ("#238636", "✓"),
    "BLOCKED": ("#b83a3a", "X"),
    "WARNING": ("#e07020", "!"),
    "FINISHED": (ACCENT, "★"),
}
ADVANCE_GROUP_COLORS = {
    "ART": "#4471c4",
    "CIVIC": "#d74343",
    "CRAFT": "#ec7c30",
    "RELIGION": "#d8bd27",
    "SCIENCE": "#6fac46",
}
ADVANCE_GROUP_LABELS = {
    "ART": "Arts",
    "CIVIC": "Civics",
    "CRAFT": "Crafts",
    "RELIGION": "Religions",
    "SCIENCE": "Sciences",
}

# Basic Rulebookin takasivun tiivistetyt oletusarvot.
DEFAULT_RULES_VALUES = (
    ("1  Tax", "2 tokens per city: stock → treasury"),
    ("2  Expansion", "1 token → +1  •  2+ tokens → +2"),
    ("3  Movement", "Token: 1 area  •  Ship: up to 4 water areas"),
    ("", "A token moves by land or ship, never both"),
    ("", "Ship capacity 5  •  No open sea by default"),
    ("", "All carried tokens disembark after the ship's final step"),
    ("", "New ship: 2 tokens / 2 treasury / 1 + 1"),
    ("", "Maintain ship: 1 token or 1 treasury"),
    ("4  Conflict", "Minority removes first  •  City attack: 7"),
    ("", "Captured city → 6 tokens  •  Gain up to 3 treasury"),
    ("5  Cities", "City site: 6 tokens  •  Wilderness: 12"),
    ("", "City support: 2 tokens per city"),
    ("6  Cards", "Stack #9 purchase: 15 treasury"),
    ("7  Trade", "At least 3 cards  •  First 2 named are true"),
    ("", "Calamities may not be named"),
    ("8  Selection", "Max 3 calamities; max 2 Major"),
    ("9  Resolution", "Token = 1 damage  •  City = 5 damage"),
    ("10  Abilities", "Use all Special Abilities in any order"),
    ("11  Support", "Remove surplus  •  Support: 2 per city"),
    ("12  Advances", "Hand limit: 8 cards (5–11 players)"),
    ("", "Hand limit: 9 cards (12–18 players)"),
    ("13  A.S.T.", "Basic, 0 cities: freeze outside Stone Age"),
    ("", "Expert, 0 cities: move back 1 outside Stone Age"),
)


def _configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 11))
    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
    style.configure("Title.TLabel", font=("Segoe UI Semibold", 25), foreground=TEXT)
    style.configure("Subtitle.TLabel", font=("Segoe UI", 12), foreground=MUTED)
    style.configure(
        "TButton",
        font=("Segoe UI Semibold", 11),
        padding=(10, 7),
        background=PANEL_ALT,
        foreground=TEXT,
    )
    style.map("TButton", background=[("active", "#31445f")])
    style.configure(
        "Accent.TButton",
        font=("Segoe UI Semibold", 12),
        background=ACCENT,
        foreground="#101010",
    )
    style.map("Accent.TButton", background=[("active", "#efc45b")])
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        font=("Segoe UI Semibold", 12),
        padding=(22, 10),
        background=PANEL,
        foreground=MUTED,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", PANEL_ALT)],
        foreground=[("selected", TEXT)],
    )


class NewGameWizard(tk.Toplevel):
    """Ohjattu uuden pelin perustaminen."""

    def __init__(
        self,
        parent: tk.Tk,
        on_complete: Callable[[GameState, Path], None],
    ) -> None:
        super().__init__(parent)
        self.title("New Mega Empires Game")
        self.configure(background=BACKGROUND)
        self.geometry("720x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", parent.destroy)

        self.on_complete = on_complete
        self.player_count = tk.IntVar(value=16)
        self.game_mode = tk.StringVar(value="BOTH")
        self.nickname = tk.StringVar()
        self.save_name = tk.StringVar()
        self.players: list[PlayerState] = []
        self.player_index = 0
        self.scenario_names: tuple[str, ...] = ()
        self.mode_buttons: dict[str, ttk.Radiobutton] = {}
        self.content = ttk.Frame(self, padding=38)
        self.content.pack(fill="both", expand=True)
        self._show_player_count()

    def _clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _show_player_count(self) -> None:
        self._clear()
        ttk.Label(
            self.content,
            text="Start a New Game",
            style="Title.TLabel",
        ).pack(anchor="w", pady=(20, 8))
        ttk.Label(
            self.content,
            text="Name the save and select the game boxes and player count.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 24))

        name_frame = ttk.Frame(self.content)
        name_frame.pack(fill="x", pady=(0, 20))
        ttk.Label(name_frame, text="Saved game name").pack(side="left")
        ttk.Entry(
            name_frame,
            textvariable=self.save_name,
            font=("Segoe UI", 13),
            width=32,
        ).pack(side="right", fill="x", expand=True, padx=(24, 0))

        mode_frame = ttk.LabelFrame(self.content, text="Game boxes", padding=14)
        mode_frame.pack(fill="x", pady=(0, 20))
        for mode in ("WEST", "EAST", "BOTH"):
            button = ttk.Radiobutton(
                mode_frame,
                text=GAME_MODE_LABELS[mode],
                value=mode,
                variable=self.game_mode,
            )
            button.pack(side="left", padx=(0, 28))
            self.mode_buttons[mode] = button

        count_frame = ttk.Frame(self.content)
        count_frame.pack(fill="x")
        ttk.Label(count_frame, text="Players").pack(side="left")
        count_box = ttk.Combobox(
            count_frame,
            textvariable=self.player_count,
            values=tuple(range(3, 19)),
            state="readonly",
            width=6,
            font=("Segoe UI", 13),
        )
        count_box.pack(side="left", padx=(24, 0))
        count_box.bind("<<ComboboxSelected>>", self._update_mode_rules)

        self.mode_note = ttk.Label(
            self.content,
            style="Subtitle.TLabel",
        )
        self.mode_note.pack(anchor="w", pady=(22, 0))
        self._update_mode_rules()

        ttk.Button(
            self.content,
            text="Next",
            style="Accent.TButton",
            command=self._start_players,
        ).pack(anchor="e", side="bottom", pady=20)

    def _update_mode_rules(self, _event: object | None = None) -> None:
        count = self.player_count.get()
        if count in {3, 4}:
            self.game_mode.set("EAST")
            self.mode_buttons["WEST"].state(["disabled"])
            self.mode_buttons["EAST"].state(["!disabled"])
            self.mode_buttons["BOTH"].state(["disabled"])
            self.mode_note.configure(
                text="The 3–4 player special scenario uses The East."
            )
        elif count >= 10:
            self.game_mode.set("BOTH")
            self.mode_buttons["WEST"].state(["disabled"])
            self.mode_buttons["EAST"].state(["disabled"])
            self.mode_buttons["BOTH"].state(["!disabled"])
            self.mode_note.configure(
                text="Games with 10–18 players always use both game boxes."
            )
        else:
            if self.game_mode.get() == "BOTH":
                self.game_mode.set("WEST")
            self.mode_buttons["WEST"].state(["!disabled"])
            self.mode_buttons["EAST"].state(["!disabled"])
            self.mode_buttons["BOTH"].state(["disabled"])
            self.mode_note.configure(
                text="For 5–9 players, choose either The West or The East."
            )

    def _start_players(self) -> None:
        self._update_mode_rules()
        try:
            save_path = save_path_for_name(self.save_name.get())
        except ValueError as error:
            messagebox.showerror("Invalid save name", str(error), parent=self)
            return
        if save_path.exists():
            messagebox.showerror(
                "Name already in use",
                "A saved game with this name already exists. "
                "Choose another name.",
                parent=self,
            )
            return
        try:
            self.scenario_names = scenario_civilizations(
                self.game_mode.get(),
                self.player_count.get(),
            )
        except ValueError as error:
            messagebox.showerror("Invalid setup", str(error), parent=self)
            return
        self.players.clear()
        self.player_index = 0
        self._show_player()

    def _show_player(self) -> None:
        self._clear()
        count = self.player_count.get()
        civilization = self.scenario_names[self.player_index]
        ttk.Label(
            self.content,
            text=f"{civilization} – Player {self.player_index + 1}/{count}",
            style="Title.TLabel",
        ).pack(anchor="w", pady=(20, 8))
        ttk.Label(
            self.content,
            text=(
                "This civilization is part of the official setup. "
                "Enter the player's first name or nickname."
            ),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 30))

        form = ttk.Frame(self.content)
        form.pack(fill="x")
        ttk.Label(form, text="Civilization").grid(
            row=0,
            column=0,
            sticky="w",
            pady=8,
        )
        civilization_label = ttk.Label(
            form,
            text=civilization,
            font=("Segoe UI Semibold", 15),
        )
        civilization_label.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(24, 0),
            pady=8,
        )

        ttk.Label(form, text="First name or nickname").grid(
            row=1,
            column=0,
            sticky="w",
            pady=8,
        )
        self.nickname.set("")
        nickname_entry = ttk.Entry(
            form,
            textvariable=self.nickname,
            font=("Segoe UI", 13),
            width=30,
        )
        nickname_entry.grid(row=1, column=1, sticky="ew", padx=(24, 0), pady=8)
        form.columnconfigure(1, weight=1)
        nickname_entry.focus_set()
        nickname_entry.bind("<Return>", lambda _event: self._accept_player())

        buttons = ttk.Frame(self.content)
        buttons.pack(side="bottom", fill="x", pady=20)
        ttk.Button(
            buttons,
            text="Back",
            command=self._previous_player,
        ).pack(side="left")
        button_text = "Start Game" if self.player_index + 1 == count else "Next"
        ttk.Button(
            buttons,
            text=button_text,
            style="Accent.TButton",
            command=self._accept_player,
        ).pack(side="right")

    def _previous_player(self) -> None:
        if self.player_index == 0:
            self._show_player_count()
            return
        previous = self.players.pop()
        self.player_index -= 1
        self._show_player()
        self.nickname.set(previous.nickname)

    def _accept_player(self) -> None:
        civilization = self.scenario_names[self.player_index]
        nickname = self.nickname.get().strip()
        if not nickname:
            messagebox.showerror(
                "Missing name",
                "Enter the player's first name or nickname.",
                parent=self,
            )
            return
        player = PlayerState(
            civilization=civilization,
            nickname=nickname,
            block=default_block(civilization, self.player_count.get()),
        )
        self.players.append(player)
        self.player_index += 1
        if self.player_index >= self.player_count.get():
            game = GameState(
                player_count=self.player_count.get(),
                players=self.players.copy(),
                game_mode=self.game_mode.get(),
            )
            self.grab_release()
            self.destroy()
            self.on_complete(game, save_path_for_name(self.save_name.get()))
        else:
            self._show_player()


class AdvanceDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        player: PlayerState,
        game: GameState,
        on_save: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.player = player
        self.game = game
        self.on_save = on_save
        self.title(f"Civilization Advances – {player.display_name}")
        self.configure(background=BACKGROUND)
        self.geometry("1400x950")
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self.variables = {
            advance.id: tk.BooleanVar(value=advance.id in player.advances)
            for advance in ADVANCES
        }
        self.flexible_entitlement = flexible_credit_entitlement(
            player.advances
        )
        self.flexible_vars = {
            group: tk.IntVar(value=player.flexible_credits.get(group, 0))
            for group in ADVANCE_GROUPS
        }
        self.credit_value_labels: dict[str, tk.Label] = {}
        self.choice_drawers: list[Callable[[], None]] = []
        self.flexible_status_label: ttk.Label | None = None
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=player.display_name,
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Select all Civilization Advances acquired by this player.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 2))
        ttk.Label(
            outer,
            text=(
                "Prices use previously saved credits and same-row discounts. "
                "Optional one-time abilities such as Library are not included."
            ),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        legend = tk.Frame(outer, background=BACKGROUND)
        legend.pack(fill="x", pady=(0, 12))
        for group_id in ("ART", "CIVIC", "CRAFT", "RELIGION", "SCIENCE"):
            color = ADVANCE_GROUP_COLORS[group_id]
            foreground = (
                "#ffffff" if group_id in {"ART", "CIVIC"} else "#101010"
            )
            block = tk.Frame(
                legend,
                background=color,
                padx=9,
                pady=5,
            )
            block.pack(side="left", fill="x", expand=True, padx=(0, 7))
            tk.Label(
                block,
                text=ADVANCE_GROUP_LABELS[group_id],
                font=("Segoe UI Semibold", 9),
                background=color,
                foreground=foreground,
            ).pack(anchor="w")
            value_label = tk.Label(
                block,
                text="0 credit",
                font=("Segoe UI Semibold", 12),
                background=color,
                foreground=foreground,
            )
            value_label.pack(side="left")
            self.credit_value_labels[group_id] = value_label
            if self.flexible_entitlement:
                tk.Label(
                    block,
                    text="Flexible:",
                    font=("Segoe UI", 8),
                    background=color,
                    foreground=foreground,
                ).pack(side="left", padx=(12, 3))
                spinbox = tk.Spinbox(
                    block,
                    from_=0,
                    to=self.flexible_entitlement,
                    increment=5,
                    width=3,
                    textvariable=self.flexible_vars[group_id],
                    command=self._refresh_credit_display,
                    justify="center",
                    font=("Segoe UI Semibold", 9),
                )
                spinbox.pack(side="left")
                spinbox.bind(
                    "<KeyRelease>",
                    lambda _event: self._refresh_credit_display(),
                )
                spinbox.bind(
                    "<FocusOut>",
                    lambda _event: self._refresh_credit_display(),
                )
        if self.flexible_entitlement:
            self.flexible_status_label = ttk.Label(
                outer,
                style="Subtitle.TLabel",
            )
            self.flexible_status_label.pack(anchor="w", pady=(0, 8))

        buttons = tk.Frame(outer, background=BACKGROUND)
        buttons.pack(side="bottom", fill="x", pady=(18, 0))
        tk.Button(
            buttons,
            text="Cancel",
            command=self.destroy,
            width=16,
            font=("Segoe UI Semibold", 12),
            background=PANEL_ALT,
            foreground=TEXT,
            activebackground="#31445f",
            activeforeground=TEXT,
            relief="flat",
            padx=16,
            pady=11,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Save Advances",
            command=self._save,
            width=18,
            font=("Segoe UI Semibold", 12),
            background=ACCENT,
            foreground="#101010",
            activebackground="#efc45b",
            activeforeground="#101010",
            relief="flat",
            padx=16,
            pady=11,
        ).pack(side="right")

        columns = ttk.Frame(outer)
        columns.pack(fill="both", expand=True)
        for column_index, victory_points in enumerate((1, 3, 6)):
            group = ttk.LabelFrame(
                columns,
                text=f"{victory_points} VP",
                padding=12,
            )
            group.grid(
                row=0,
                column=column_index,
                sticky="nsew",
                padx=(0 if column_index == 0 else 8, 0),
            )
            advances = [
                advance
                for advance in ADVANCES
                if advance.victory_points == victory_points
            ]
            for row_index, advance in enumerate(advances):
                self._advance_choice(group, advance).grid(
                    row=row_index,
                    column=0,
                    sticky="ew",
                    pady=2,
                )
            group.columnconfigure(0, weight=1)
            columns.columnconfigure(column_index, weight=1)
        columns.rowconfigure(0, weight=1)
        self._refresh_credit_display()

    def _working_flexible_credits(self) -> dict[str, int]:
        values: dict[str, int] = {}
        for group in ADVANCE_GROUPS:
            try:
                values[group] = max(0, int(self.flexible_vars[group].get()))
            except (tk.TclError, ValueError):
                values[group] = 0
        return values

    def _refresh_credit_display(self) -> None:
        flexible = self._working_flexible_credits()
        totals = color_credits(
            self.player,
            self.game.player_count,
            flexible,
        )
        for group, label in self.credit_value_labels.items():
            label.configure(text=f"{totals[group]} credit")
        if self.flexible_status_label is not None:
            allocated = sum(flexible.values())
            self.flexible_status_label.configure(
                text=(
                    f"Flexible credits assigned: {allocated} / "
                    f"{self.flexible_entitlement}"
                )
            )
        for draw in self.choice_drawers:
            draw()

    def _advance_choice(
        self,
        parent: tk.Widget,
        advance: Advance,
    ) -> tk.Canvas:
        height = 28
        canvas = tk.Canvas(
            parent,
            height=height,
            width=350,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            takefocus=True,
        )

        def draw(_event: object | None = None) -> None:
            width = max(canvas.winfo_width(), 330)
            canvas.delete("all")
            colors = [
                ADVANCE_GROUP_COLORS[group_id]
                for group_id in advance.groups
            ]
            segment_width = width / len(colors)
            for index, color in enumerate(colors):
                canvas.create_rectangle(
                    index * segment_width,
                    0,
                    (index + 1) * segment_width,
                    height,
                    fill=color,
                    outline=color,
                )

            selected = self.variables[advance.id].get()
            canvas.create_rectangle(
                1,
                1,
                width - 1,
                height - 1,
                outline=ACCENT if selected else "#dce3eb",
                width=3 if selected else 1,
            )
            canvas.create_rectangle(
                8,
                6,
                24,
                22,
                fill="#ffffff",
                outline="#101722",
                width=1,
            )
            if selected:
                canvas.create_text(
                    16,
                    14,
                    text="✓",
                    fill="#176b2c",
                    font=("Segoe UI Semibold", 12),
                )

            price = advance_price(
                advance,
                self.player,
                self.game.player_count,
                self._working_flexible_credits(),
            )
            label = advance.name
            price_label = (
                "OWNED"
                if advance.id in self.player.advances
                else (
                    str(price.effective_cost)
                    if price.effective_cost == price.base_cost
                    else f"{price.base_cost} → {price.effective_cost}"
                )
            )
            canvas.create_text(
                33,
                15,
                text=label,
                anchor="w",
                fill="#101010",
                font=("Segoe UI Semibold", 10),
            )
            canvas.create_text(
                32,
                14,
                text=label,
                anchor="w",
                fill="#ffffff",
                font=("Segoe UI Semibold", 10),
            )
            canvas.create_text(
                width - 9,
                15,
                text=price_label,
                anchor="e",
                fill="#101010",
                font=("Segoe UI Semibold", 10),
            )
            canvas.create_text(
                width - 10,
                14,
                text=price_label,
                anchor="e",
                fill="#ffffff",
                font=("Segoe UI Semibold", 10),
            )

        def toggle(_event: object | None = None) -> str:
            variable = self.variables[advance.id]
            variable.set(not variable.get())
            draw()
            return "break"

        canvas.bind("<Configure>", draw)
        canvas.bind("<Button-1>", toggle)
        canvas.bind("<space>", toggle)
        canvas.bind("<Return>", toggle)
        self.choice_drawers.append(draw)
        draw()
        return canvas

    def _save(self) -> None:
        selected_advances = [
            advance.id
            for advance in ADVANCES
            if self.variables[advance.id].get()
        ]
        flexible = self._working_flexible_credits()
        entitlement = flexible_credit_entitlement(selected_advances)
        allocated = sum(flexible.values())
        if allocated > entitlement or any(
            value % 5 for value in flexible.values()
        ):
            messagebox.showerror(
                "Check flexible credits",
                "Flexible credits must be assigned in multiples of 5 and "
                f"cannot exceed {entitlement} points for the selected "
                "Advances.",
                parent=self,
            )
            return
        self.player.advances = selected_advances
        self.player.flexible_credits = flexible
        self.player.normalize()
        self.on_save()
        self.grab_release()
        self.destroy()


class PlayerDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        player: PlayerState,
        game: GameState,
        on_save: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.player = player
        self.game = game
        self.on_save = on_save
        self.title(f"Edit – {player.display_name}")
        self.configure(background=BACKGROUND)
        self.geometry("600x520")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self.nickname = tk.StringVar(value=player.nickname)
        self.block = tk.StringVar(value=player.block)
        self.cities = tk.IntVar(value=player.cities)
        self.ast_step = tk.IntVar(value=player.ast_step)
        self.census = tk.IntVar(value=player.census)
        self.ast_bonus = tk.BooleanVar(value=player.ast_bonus)

        outer = ttk.Frame(self, padding=30)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=player.civilization, style="Title.TLabel").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 20),
        )
        fields = (
            ("First name or nickname", ttk.Entry(outer, textvariable=self.nickname)),
            (
                "Trade block",
                ttk.Combobox(
                    outer,
                    textvariable=self.block,
                    values=(
                        ("SINGLE",)
                        if game.game_mode == "BOTH" and game.player_count <= 11
                        else ("WEST", "EAST")
                    ),
                    state="readonly",
                ),
            ),
            (
                "Cities",
                ttk.Spinbox(outer, from_=0, to=9, textvariable=self.cities),
            ),
            (
                "A.S.T. step (0–15)",
                ttk.Spinbox(
                    outer,
                    from_=0,
                    to=AST_MAX_STEP,
                    textvariable=self.ast_step,
                ),
            ),
            (
                "Census (0–55)",
                ttk.Spinbox(outer, from_=0, to=55, textvariable=self.census),
            ),
        )
        for row, (label, widget) in enumerate(fields, start=1):
            ttk.Label(outer, text=label).grid(row=row, column=0, sticky="w", pady=8)
            widget.grid(row=row, column=1, sticky="ew", padx=(24, 0), pady=8)
        ttk.Checkbutton(
            outer,
            text="Confirmed A.S.T. end-game bonus (+5 VP)",
            variable=self.ast_bonus,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 4))
        ttk.Label(
            outer,
            text="Confirm the bonus only during the final A.S.T. phase.",
            style="Subtitle.TLabel",
        ).grid(row=7, column=0, columnspan=2, sticky="w")
        outer.columnconfigure(1, weight=1)

        buttons = ttk.Frame(outer)
        buttons.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(26, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")
        ttk.Button(
            buttons,
            text="Save",
            style="Accent.TButton",
            command=self._save,
        ).pack(side="right")

    def _save(self) -> None:
        nickname = self.nickname.get().strip()
        if not nickname:
            messagebox.showerror(
                "Missing name",
                "Enter the player's first name or nickname.",
                parent=self,
            )
            return
        try:
            cities = int(self.cities.get())
            ast_step = int(self.ast_step.get())
            census = int(self.census.get())
        except (ValueError, tk.TclError):
            messagebox.showerror(
                "Invalid number",
                "Check the values for Cities, A.S.T. step, and Census.",
                parent=self,
            )
            return
        if not 0 <= cities <= 9 or not 0 <= ast_step <= 15 or not 0 <= census <= 55:
            messagebox.showerror(
                "Value outside the allowed range",
                "Cities: 0–9, A.S.T.: 0–15, and Census: 0–55.",
                parent=self,
            )
            return

        requested_bonus = self.ast_bonus.get()
        other_bonus_players = [
            other
            for other in self.game.players
            if other is not self.player and other.ast_bonus
        ]
        if (
            requested_bonus
            and self.game.player_count <= 11
            and other_bonus_players
        ):
            messagebox.showerror(
                "Cannot award A.S.T. bonus",
                "The A.S.T. end-game bonus can be confirmed for only one "
                "player in this game.",
                parent=self,
            )
            return
        if (
            requested_bonus
            and self.game.player_count >= 12
            and len(other_bonus_players) >= 2
        ):
            messagebox.showerror(
                "Cannot award A.S.T. bonus",
                "The bonus can be confirmed for no more than two players "
                "in a combined game.",
                parent=self,
            )
            return
        if (
            requested_bonus
            and self.game.player_count >= 12
            and len(other_bonus_players) == 1
            and other_bonus_players[0].block == self.block.get()
        ):
            messagebox.showerror(
                "Cannot award A.S.T. bonus",
                "Two bonus recipients must belong to different trade blocks.",
                parent=self,
            )
            return

        self.player.nickname = nickname
        self.player.block = self.block.get()
        self.player.cities = cities
        self.player.ast_step = ast_step
        self.player.census = census
        self.player.ast_bonus = requested_bonus
        self.player.normalize()
        self.on_save()
        self.grab_release()
        self.destroy()


class SavedGameDialog(tk.Toplevel):
    """Tallennetun pelin valinta tai uuden pelin aloitus."""

    def __init__(
        self,
        parent: tk.Tk,
        saves: tuple[SavedGame, ...],
        on_open: Callable[[Path], None],
        on_new: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.title("Mega Empires – Saved Games")
        self.configure(background=BACKGROUND)
        self.geometry("760x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", parent.destroy)
        self.saves = saves
        self.on_open = on_open
        self.on_new = on_new

        content = ttk.Frame(self, padding=38)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text="Choose a Saved Game",
            style="Title.TLabel",
        ).pack(anchor="w", pady=(10, 8))
        ttk.Label(
            content,
            text="Continue an existing game or start a new one.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 22))

        self.tree = ttk.Treeview(
            content,
            columns=("players", "mode", "saved"),
            show="tree headings",
            height=12,
            selectmode="browse",
        )
        self.tree.heading("#0", text="Saved game")
        self.tree.heading("players", text="Players")
        self.tree.heading("mode", text="Game")
        self.tree.heading("saved", text="Last saved")
        self.tree.column("#0", width=220)
        self.tree.column("players", width=75, anchor="center")
        self.tree.column("mode", width=145)
        self.tree.column("saved", width=190)
        self.tree.pack(fill="both", expand=True)
        for index, save in enumerate(saves):
            saved_at = save.saved_at.replace("T", " ")[:16]
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                text=save.name,
                values=(
                    save.player_count,
                    GAME_MODE_LABELS.get(save.game_mode, save.game_mode),
                    saved_at,
                ),
            )
        if saves:
            self.tree.selection_set("0")
            self.tree.focus("0")
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())

        buttons = ttk.Frame(content)
        buttons.pack(fill="x", pady=(20, 0))
        ttk.Button(
            buttons,
            text="New Game",
            command=self._new_game,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Continue",
            style="Accent.TButton",
            command=self._open_selected,
        ).pack(side="right")

    def _close(self) -> None:
        self.grab_release()
        self.destroy()

    def _new_game(self) -> None:
        self._close()
        self.on_new()

    def _open_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showerror(
                "No saved game selected",
                "Select a saved game to continue.",
                parent=self,
            )
            return
        path = self.saves[int(selection[0])].path
        self._close()
        self.on_open(path)


class MegaEmpiresApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.game: GameState | None = None
        self.save_path: Path | None = None
        root.title("Mega Empires – Score Tracker")
        root.configure(background=BACKGROUND)
        root.minsize(1280, 720)
        root.geometry("1920x1080")
        _configure_styles(root)
        self._startup()

    def _startup(self) -> None:
        saves = list_saved_games()
        if not saves:
            self._new_game()
            return
        SavedGameDialog(
            self.root,
            saves,
            self._load_selected_game,
            self._new_game,
        )

    def _load_selected_game(self, path: Path) -> None:
        try:
            self._open_game(load_game(path), path)
        except (OSError, ValueError, KeyError) as error:
            messagebox.showerror(
                "Could not open saved game",
                f"The saved game could not be opened:\n{error}",
                parent=self.root,
            )
            self._startup()

    def _new_game(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        NewGameWizard(self.root, self._open_game)

    def _open_game(self, game: GameState, path: Path) -> None:
        self.game = game
        self.save_path = path
        self._save()
        self._build_main_view()

    def _save(self) -> None:
        if self.game is not None and self.save_path is not None:
            save_game(self.game, self.save_path)

    def _save_and_refresh(self) -> None:
        self._save()
        self._refresh_all()

    def _build_main_view(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

        header = ttk.Frame(self.root, padding=(24, 14))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="MEGA EMPIRES",
            style="Title.TLabel",
        ).pack(side="left")
        self.status_label = ttk.Label(header, style="Subtitle.TLabel")
        self.status_label.pack(side="left", padx=24)
        ttk.Button(
            header,
            text="New Game",
            command=self._confirm_new_game,
        ).pack(side="right")
        turn_control = tk.Frame(header, background=BACKGROUND)
        turn_control.pack(side="right", padx=(0, 18))
        tk.Label(
            turn_control,
            text="TURN",
            font=("Segoe UI Semibold", 11),
            background=BACKGROUND,
            foreground=MUTED,
        ).pack(side="left", padx=(0, 7))
        tk.Button(
            turn_control,
            text="−",
            command=lambda: self._change_round(-1),
            width=2,
            font=("Segoe UI Semibold", 12),
            background=PANEL_ALT,
            foreground=TEXT,
            activebackground="#31445f",
            activeforeground=TEXT,
            relief="flat",
        ).pack(side="left")
        self.turn_label = tk.Label(
            turn_control,
            text="1",
            width=3,
            font=("Segoe UI Semibold", 14),
            background=PANEL,
            foreground=ACCENT,
        )
        self.turn_label.pack(side="left", padx=3)
        tk.Button(
            turn_control,
            text="+",
            command=lambda: self._change_round(1),
            width=2,
            font=("Segoe UI Semibold", 12),
            background=PANEL_ALT,
            foreground=TEXT,
            activebackground="#31445f",
            activeforeground=TEXT,
            relief="flat",
        ).pack(side="left")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.summary_tab = ttk.Frame(self.notebook)
        self.ast_tab = ttk.Frame(self.notebook)
        self.sequence_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.summary_tab, text="Scoreboard")
        self.notebook.add(self.ast_tab, text="A.S.T.")
        self.notebook.add(self.sequence_tab, text="Sequence of Play")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._refresh_all()

    def _confirm_new_game(self) -> None:
        if messagebox.askyesno(
            "Start a new game?",
            "The current game remains in the latest save only until the new "
            "game is created. Do you want to continue?",
            icon="warning",
            parent=self.root,
        ):
            self.game = None
            self.save_path = None
            self._new_game()

    def _refresh_all(self) -> None:
        if self.game is None:
            return
        self._refresh_header()
        self._refresh_summary()
        self._refresh_ast()
        self._refresh_sequence()

    def _refresh_header(self) -> None:
        if self.game is None:
            return
        save_name = self.save_path.stem if self.save_path is not None else ""
        self.status_label.configure(
            text=(
                f"{save_name}  •  "
                f"{GAME_MODE_LABELS[self.game.game_mode]}  •  "
                f"{self.game.player_count} players  •  "
                f"{self.game.ast_variant.title()} A.S.T.  •  "
                f"Turn {self.game.round_number}  •  "
                "Autosave enabled"
            )
        )
        self.turn_label.configure(text=str(self.game.round_number))

    def _change_round(self, amount: int) -> None:
        if self.game is None:
            return
        self.game.round_number = max(1, self.game.round_number + amount)
        self._save()
        self._refresh_header()
        self._refresh_sequence()

    def _on_tab_changed(self, _event: object | None = None) -> None:
        if self.game is None or not hasattr(self, "sequence_tab"):
            return
        if self.notebook.select() == str(self.sequence_tab):
            self._refresh_sequence()

    def _change_cities(self, player: PlayerState, amount: int) -> None:
        player.cities = max(0, min(9, player.cities + amount))
        self._save_and_refresh()

    def _change_ast(self, player: PlayerState, amount: int) -> None:
        player.ast_step = max(0, min(AST_MAX_STEP, player.ast_step + amount))
        self._save_and_refresh()

    def _refresh_summary(self) -> None:
        if self.game is None:
            return
        for child in self.summary_tab.winfo_children():
            child.destroy()

        ordered = players_in_ast_order(self.game.players)
        rankings = visible_rankings(self.game.players)
        board = ttk.Frame(self.summary_tab, padding=8)
        board.pack(fill="both", expand=True)
        board.columnconfigure(0, weight=1, uniform="players")
        board.columnconfigure(1, weight=1, uniform="players")

        split_index = (len(ordered) + 1) // 2
        maximum_rows = max(split_index, len(ordered) - split_index)
        row_height = 90 if maximum_rows >= 9 else 103
        for index, player in enumerate(ordered):
            column = 0 if index < split_index else 1
            row = index if column == 0 else index - split_index
            self._create_player_row(
                board,
                player,
                rankings[player.civilization],
                row,
                column,
                row_height,
            )

    def _create_player_row(
        self,
        parent: ttk.Frame,
        player: PlayerState,
        ranking: int,
        row: int,
        column: int,
        row_height: int,
    ) -> None:
        civilization = CIVILIZATION_BY_NAME[player.civilization]
        score = calculate_score(player)
        card_count = len(player.advances)

        outer = tk.Frame(
            parent,
            background=PANEL,
            highlightbackground="#344258",
            highlightthickness=1,
            height=row_height,
        )
        outer.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 5, 5 if column == 0 else 0),
            pady=3,
        )
        outer.grid_propagate(False)
        parent.rowconfigure(row, weight=1)

        badge = tk.Label(
            outer,
            text=str(ranking),
            font=("Segoe UI Semibold", 22),
            width=3,
            background=civilization.color,
            foreground=civilization.text_color,
        )
        badge.pack(side="left", fill="y")

        identity = tk.Frame(outer, background=PANEL, width=215)
        identity.pack(side="left", fill="y", padx=(12, 5), pady=8)
        identity.pack_propagate(False)
        tk.Label(
            identity,
            text=player.display_name,
            anchor="w",
            font=("Segoe UI Semibold", 15),
            background=PANEL,
            foreground=TEXT,
        ).pack(fill="x")
        tk.Label(
            identity,
            text=(
                f"{player.block}  •  {card_count} Advances"
                + ("  •  A.S.T. bonus" if player.ast_bonus else "")
            ),
            anchor="w",
            font=("Segoe UI", 10),
            background=PANEL,
            foreground=MUTED,
        ).pack(fill="x", pady=(5, 0))

        score_frame = tk.Frame(outer, background=PANEL, width=105)
        score_frame.pack(side="left", fill="y", pady=7)
        score_frame.pack_propagate(False)
        tk.Label(
            score_frame,
            text=str(score.total),
            font=("Segoe UI Semibold", 28),
            background=PANEL,
            foreground=ACCENT,
        ).pack()
        tk.Label(
            score_frame,
            text=f"{score.cities}+{score.ast}+{score.advances}+{score.bonus}",
            font=("Segoe UI", 9),
            background=PANEL,
            foreground=MUTED,
        ).pack()

        controls = tk.Frame(outer, background=PANEL)
        controls.pack(side="left", fill="both", expand=True, padx=5, pady=7)
        self._counter(
            controls,
            "Cities",
            player.cities,
            lambda: self._change_cities(player, -1),
            lambda: self._change_cities(player, 1),
        ).pack(side="left", padx=4)
        self._counter(
            controls,
            "A.S.T.",
            f"{player.ast_step} / {score.ast} VP",
            lambda: self._change_ast(player, -1),
            lambda: self._change_ast(player, 1),
        ).pack(side="left", padx=4)
        self._census_editor(controls, player).pack(side="left", padx=4)

        actions = tk.Frame(outer, background=PANEL)
        actions.pack(side="right", fill="y", padx=(4, 10), pady=7)
        ttk.Button(
            actions,
            text="Advances",
            width=8,
            command=lambda: AdvanceDialog(
                self.root,
                player,
                self.game,
                self._save_and_refresh,
            ),
        ).pack(pady=(0, 3))
        ttk.Button(
            actions,
            text="Details",
            width=8,
            command=lambda: PlayerDialog(
                self.root,
                player,
                self.game,
                self._save_and_refresh,
            ),
        ).pack()

    def _counter(
        self,
        parent: tk.Widget,
        title: str,
        value: int | str,
        decrement: Callable[[], None],
        increment: Callable[[], None],
    ) -> tk.Frame:
        frame = tk.Frame(parent, background=PANEL_ALT)
        tk.Label(
            frame,
            text=title,
            font=("Segoe UI", 9),
            background=PANEL_ALT,
            foreground=MUTED,
        ).pack()
        row = tk.Frame(frame, background=PANEL_ALT)
        row.pack()
        tk.Button(
            row,
            text="−",
            command=decrement,
            width=2,
            font=("Segoe UI Semibold", 12),
            background="#31445f",
            foreground=TEXT,
            relief="flat",
        ).pack(side="left")
        tk.Label(
            row,
            text=str(value),
            width=8,
            font=("Segoe UI Semibold", 11),
            background=PANEL_ALT,
            foreground=TEXT,
        ).pack(side="left")
        tk.Button(
            row,
            text="+",
            command=increment,
            width=2,
            font=("Segoe UI Semibold", 12),
            background="#31445f",
            foreground=TEXT,
            relief="flat",
        ).pack(side="left")
        return frame

    def _census_editor(
        self,
        parent: tk.Widget,
        player: PlayerState,
    ) -> tk.Frame:
        frame = tk.Frame(parent, background=PANEL_ALT)
        tk.Label(
            frame,
            text="Census",
            font=("Segoe UI", 9),
            background=PANEL_ALT,
            foreground=MUTED,
        ).pack()

        value = tk.StringVar(value=str(player.census))

        def valid_input(proposed: str) -> bool:
            return proposed == "" or (
                proposed.isdigit() and 0 <= int(proposed) <= 55
            )

        entry = tk.Entry(
            frame,
            textvariable=value,
            width=5,
            justify="center",
            font=("Segoe UI Semibold", 12),
            background="#31445f",
            foreground=TEXT,
            insertbackground=TEXT,
            relief="flat",
            validate="key",
            validatecommand=(self.root.register(valid_input), "%P"),
        )
        entry.pack(padx=6, pady=(2, 3), ipady=3)
        entry.bind(
            "<KeyRelease>",
            lambda _event: self._commit_census(player, value),
        )
        entry.bind(
            "<FocusOut>",
            lambda _event: (
                value.set(str(player.census))
                if value.get() == ""
                else self._commit_census(player, value)
            ),
        )
        entry.bind(
            "<Return>",
            lambda _event: self._commit_census(player, value),
        )
        return frame

    def _commit_census(
        self,
        player: PlayerState,
        value: tk.StringVar,
    ) -> None:
        text = value.get()
        if not text:
            return
        census = int(text)
        if census != player.census:
            player.census = census
            self._save()

    def _refresh_sequence(self) -> None:
        if self.game is None:
            return
        for child in self.sequence_tab.winfo_children():
            child.destroy()

        header = ttk.Frame(self.sequence_tab, padding=(18, 12))
        header.pack(fill="x")
        current = PHASE_BY_NUMBER[self.game.current_phase]
        ttk.Label(
            header,
            text=(
                f"TURN {self.game.round_number}  •  "
                f"PHASE {current.number} OF {len(PHASES)}"
            ),
            style="Title.TLabel",
        ).pack(side="left")

        ttk.Button(
            header,
            text="Next Phase  >",
            style="Accent.TButton",
            command=lambda: self._change_phase(1),
        ).pack(side="right")
        ttk.Button(
            header,
            text="<  Previous Phase",
            command=lambda: self._change_phase(-1),
        ).pack(side="right", padx=(0, 10))

        content = ttk.Frame(self.sequence_tab, padding=(18, 0, 18, 18))
        content.pack(fill="both", expand=True)

        phase_list = tk.Frame(content, background=BACKGROUND, width=368)
        phase_list.pack(side="left", fill="y", padx=(0, 16))
        phase_list.pack_propagate(False)
        for phase in PHASES:
            selected = phase.number == self.game.current_phase
            order_summary = self._phase_order_summary(phase)
            button = tk.Button(
                phase_list,
                text=(
                    f"{phase.number:>2}.  {phase.name}\n"
                    f"      {order_summary}"
                ),
                command=lambda number=phase.number: self._select_phase(number),
                anchor="w",
                justify="left",
                font=("Segoe UI Semibold" if selected else "Segoe UI", 10),
                background=ACCENT if selected else PANEL,
                foreground="#101010" if selected else TEXT,
                activebackground="#efc45b" if selected else PANEL_ALT,
                activeforeground="#101010" if selected else TEXT,
                relief="flat",
                bd=0,
                padx=12,
                pady=5,
                wraplength=330,
            )
            button.pack(fill="x", pady=(0, 3))

        summary = tk.Frame(content, background=PANEL, width=400)
        summary.pack(side="right", fill="y", padx=(16, 0))
        summary.pack_propagate(False)
        self._render_default_rules(summary, current.number)

        detail = tk.Frame(content, background=PANEL, padx=24, pady=18)
        detail.pack(side="left", fill="both", expand=True)
        self._render_phase_detail(detail, current)

    def _render_default_rules(
        self,
        parent: tk.Frame,
        current_phase: int,
    ) -> None:
        phase = PHASE_BY_NUMBER[current_phase]
        tk.Label(
            parent,
            text="DEFAULT RULES / VALUES",
            anchor="w",
            font=("Segoe UI Semibold", 17),
            background=PANEL,
            foreground=ACCENT,
            padx=18,
            pady=15,
        ).pack(fill="x")
        tk.Label(
            parent,
            text=f"{current_phase}. {phase.name}",
            anchor="w",
            font=("Segoe UI Semibold", 13),
            background=PANEL,
            foreground=TEXT,
            padx=18,
        ).pack(fill="x", pady=(0, 14))

        phase_number = 0
        active_values: list[str] = []
        for heading, value in DEFAULT_RULES_VALUES:
            if heading:
                phase_number = int(heading.split(maxsplit=1)[0])
            if phase_number == current_phase:
                active_values.append(value)

        for value in active_values:
            tk.Label(
                parent,
                text=f"•  {value}",
                anchor="nw",
                justify="left",
                wraplength=350,
                font=("Segoe UI", 12),
                background=PANEL,
                foreground=TEXT,
                padx=18,
                pady=6,
            ).pack(fill="x")

        special_rules = self._small_east_phase_rules(phase)
        if special_rules:
            tk.Frame(parent, background="#344258", height=1).pack(
                fill="x",
                padx=18,
                pady=(14, 10),
            )
            tk.Label(
                parent,
                text="3–4 PLAYER EAST",
                anchor="w",
                font=("Segoe UI Semibold", 11),
                background=PANEL,
                foreground=ACCENT,
                padx=18,
            ).pack(fill="x")
            for rule in special_rules:
                tk.Label(
                    parent,
                    text=f"•  {rule.removeprefix('3–4 PLAYER EAST: ')}",
                    anchor="nw",
                    justify="left",
                    wraplength=350,
                    font=("Segoe UI", 11),
                    background=PANEL,
                    foreground=TEXT,
                    padx=18,
                    pady=5,
                ).pack(fill="x")

    def _select_phase(self, phase_number: int) -> None:
        if self.game is None:
            return
        self.game.current_phase = max(1, min(len(PHASES), phase_number))
        self._save()
        self._refresh_sequence()

    def _change_phase(self, direction: int) -> None:
        if self.game is None:
            return
        self.game.round_number, self.game.current_phase = adjacent_phase(
            self.game.round_number,
            self.game.current_phase,
            direction,
        )
        self._save()
        self._refresh_header()
        self._refresh_sequence()

    def _render_phase_detail(self, parent: tk.Frame, phase: Phase) -> None:
        if self.game is None:
            return
        tk.Label(
            parent,
            text=f"{phase.number}. {phase.name}",
            anchor="w",
            font=("Segoe UI Semibold", 25),
            background=PANEL,
            foreground=TEXT,
        ).pack(fill="x")
        tk.Label(
            parent,
            text=self._phase_order_summary(phase).upper(),
            anchor="w",
            font=("Segoe UI Semibold", 13),
            background=ACCENT,
            foreground="#101010",
            padx=12,
            pady=7,
        ).pack(fill="x", pady=(10, 12))

        if phase.player_order is None:
            tk.Label(
                parent,
                text="No player-by-player order is required in this phase.",
                anchor="w",
                font=("Segoe UI Semibold", 14),
                background=PANEL,
                foreground=MUTED,
            ).pack(fill="x", pady=(28, 0))
            return

        tk.Frame(parent, background="#344258", height=1).pack(
            fill="x",
            pady=(16, 12),
        )
        tk.Label(
            parent,
            text=phase.player_order_heading,
            anchor="w",
            font=("Segoe UI Semibold", 15),
            background=PANEL,
            foreground=TEXT,
        ).pack(fill="x", pady=(0, 7))

        ordered = phase_order(phase, self.game.players)
        if not ordered:
            message = (
                "No participating player currently owns a Special Ability "
                "advance."
                if phase.player_order == "special_progress"
                else "No player currently qualifies for this phase."
            )
            tk.Label(
                parent,
                text=message,
                anchor="w",
                font=("Segoe UI", 12),
                background=PANEL,
                foreground=MUTED,
            ).pack(fill="x")
            return

        order_panel = tk.Frame(parent, background=PANEL)
        order_panel.pack(fill="x")
        for index, player in enumerate(ordered, start=1):
            civilization = CIVILIZATION_BY_NAME[player.civilization]
            row = tk.Frame(
                order_panel,
                background=PANEL_ALT if index % 2 else "#1d2a3b",
                height=27,
            )
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            tk.Label(
                row,
                text=str(index),
                width=3,
                font=("Segoe UI Semibold", 10),
                background=civilization.color,
                foreground=civilization.text_color,
            ).pack(side="left", fill="y")
            tk.Label(
                row,
                text=player.display_name,
                anchor="w",
                font=("Segoe UI Semibold", 10),
                background=row.cget("background"),
                foreground=TEXT,
                padx=10,
            ).pack(side="left", fill="both", expand=True)
            tk.Label(
                row,
                text=self._phase_order_detail(phase, player),
                anchor="e",
                font=("Segoe UI", 9),
                background=row.cget("background"),
                foreground=MUTED,
                padx=10,
            ).pack(side="right", fill="y")

        if phase.player_order == "city_count":
            excluded = sum(player.cities == 0 for player in self.game.players)
            if excluded:
                tk.Label(
                    parent,
                    text=(
                        f"{excluded} player"
                        f"{'s' if excluded != 1 else ''} with 0 cities "
                        "receive no trade cards."
                    ),
                    anchor="w",
                    font=("Segoe UI", 10),
                    background=PANEL,
                    foreground=MUTED,
                ).pack(fill="x", pady=(6, 0))

    def _phase_order_summary(self, phase: Phase) -> str:
        if (
            self.game is not None
            and self.game.game_mode == "EAST"
            and self.game.player_count in {3, 4}
            and phase.number == 7
        ):
            return "Priority order; up to 6 market rounds"
        return phase.order_summary

    def _small_east_phase_rules(self, phase: Phase) -> tuple[str, ...]:
        """Lisää 3–4 pelaajan East-skenaarion olennaiset pöytämuistutukset."""

        if (
            self.game is None
            or self.game.game_mode != "EAST"
            or self.game.player_count not in {3, 4}
        ):
            return ()
        if phase.number == 6:
            return (
                "3–4 PLAYER EAST: Set up the Market board after regular "
                "dealing: add 1 Water card and one face-down card from each "
                "stack through the highest city count.",
                "Players may buy any number of Water cards for 2 treasury "
                "tokens each.",
            )
        if phase.number == 7:
            return (
                "3–4 PLAYER EAST: In priority order, trade with the Market "
                "board or pass. Repeat until everyone passes consecutively "
                "or 6 market rounds have been completed.",
                "A trade always places exactly 2 cards and takes exactly 2 "
                "different cards whose total value is no higher.",
            )
        if phase.number == 8:
            return (
                "3–4 PLAYER EAST: Reveal all face-down Market board cards "
                "after trading ends.",
            )
        if phase.number == 9:
            return (
                "3–4 PLAYER EAST: Use the dedicated 3–4 player Calamity "
                "Quick Chart and resolve calamities remaining on the Market.",
            )
        if phase.number == 13:
            return (
                "3–4 PLAYER EAST: Discard all remaining Market cards, "
                "shuffle the discards, and place them under their stacks.",
            )
        return ()

    def _phase_order_detail(self, phase: Phase, player: PlayerState) -> str:
        civilization = CIVILIZATION_BY_NAME[player.civilization]
        if phase.player_order == "movement":
            suffix = "  •  MILITARY — after non-holders" if (
                "military" in player.advances
            ) else ""
            return f"Census {player.census}{suffix}"
        if phase.player_order == "city_count":
            return f"{player.cities} {'city' if player.cities == 1 else 'cities'}"
        if phase.player_order in {"ast_progress", "special_progress"}:
            detail = f"A.S.T. step {player.ast_step}  •  {player.ast_step * 5} VP"
            if phase.player_order == "special_progress":
                abilities = sorted(
                    ADVANCE_BY_ID[advance_id].name
                    for advance_id in player.advances
                    if advance_id in SPECIAL_ABILITY_ADVANCES
                )
                detail += "  •  " + ", ".join(abilities)
            return detail
        return f"A.S.T. rank #{civilization.ast_rank}"

    def _refresh_ast(self) -> None:
        if self.game is None:
            return
        for child in self.ast_tab.winfo_children():
            child.destroy()

        info = ttk.Frame(self.ast_tab, padding=(18, 12))
        info.pack(fill="x")
        ttk.Label(
            info,
            text="Basic A.S.T. – participating civilizations only",
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(
            info,
            text="Click a space to move a marker  •  Each step = 5 VP",
            style="Subtitle.TLabel",
        ).pack(side="right")

        legend = ttk.Frame(self.ast_tab, padding=(18, 0, 18, 8))
        legend.pack(fill="x")
        for era_index, (abbreviation, name) in enumerate(
            zip(AST_ERA_ABBREVIATIONS, AST_ERA_NAMES, strict=True)
        ):
            item = tk.Frame(legend, background=AST_ERA_COLORS[era_index])
            item.pack(side="left", padx=(0, 8))
            tk.Label(
                item,
                text=f"{abbreviation}  {name}",
                background=AST_ERA_COLORS[era_index],
                foreground=TEXT,
                font=("Segoe UI Semibold", 9),
                padx=8,
                pady=4,
            ).pack()

        body = ttk.Frame(self.ast_tab)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        requirements = tk.Frame(
            body,
            background=PANEL,
            width=390,
            padx=14,
            pady=12,
        )
        requirements.pack(side="right", fill="y", padx=(14, 0))
        requirements.pack_propagate(False)
        self._build_ast_requirements_panel(requirements)

        canvas = tk.Canvas(
            body,
            background=BACKGROUND,
            highlightthickness=0,
        )
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind(
            "<Configure>",
            lambda _event: self._draw_ast(canvas),
        )

    def _build_ast_requirements_panel(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text="BASIC ERA REQUIREMENTS",
            anchor="w",
            font=("Segoe UI Semibold", 15),
            background=PANEL,
            foreground=TEXT,
        ).pack(fill="x", pady=(0, 8))
        for era_index, requirement in enumerate(BASIC_AST_REQUIREMENTS):
            card = tk.Frame(
                parent,
                background=AST_ERA_COLORS[era_index],
                padx=10,
                pady=7,
            )
            card.pack(fill="x", pady=3)
            tk.Label(
                card,
                text=(
                    f"{AST_ERA_ABBREVIATIONS[era_index]}  "
                    f"{requirement.era}"
                ),
                anchor="w",
                font=("Segoe UI Semibold", 10),
                background=AST_ERA_COLORS[era_index],
                foreground=TEXT,
            ).pack(fill="x")
            tk.Label(
                card,
                text=requirement.description,
                anchor="w",
                justify="left",
                wraplength=335,
                font=("Segoe UI", 9),
                background=AST_ERA_COLORS[era_index],
                foreground="#e2e8ef",
            ).pack(fill="x", pady=(2, 0))

        tk.Label(
            parent,
            text="MARKER STATUS",
            anchor="w",
            font=("Segoe UI Semibold", 12),
            background=PANEL,
            foreground=TEXT,
        ).pack(fill="x", pady=(14, 5))
        status_rows = (
            ("READY", "Requirements for entering the next era are met."),
            ("BLOCKED", "Requirements for entering the next era are not met."),
            (
                "WARNING",
                "Current-era requirements are no longer met. In Basic this "
                "blocks progress but does not cause regression.",
            ),
            ("FINISHED", "Final A.S.T. step reached."),
        )
        for state, description in status_rows:
            color, symbol = AST_MARKER_STYLES[state]
            row = tk.Frame(parent, background=PANEL)
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=symbol,
                width=2,
                font=("Segoe UI Semibold", 11),
                background=color,
                foreground="#ffffff" if state != "FINISHED" else "#101010",
            ).pack(side="left")
            tk.Label(
                row,
                text=description,
                anchor="w",
                justify="left",
                wraplength=315,
                font=("Segoe UI", 8),
                background=PANEL,
                foreground=MUTED,
                padx=7,
            ).pack(side="left", fill="x", expand=True)

    def _draw_ast(self, canvas: tk.Canvas) -> None:
        if self.game is None:
            return
        canvas.delete("all")
        players = sorted(
            self.game.players,
            key=lambda player: CIVILIZATION_BY_NAME[player.civilization].ast_rank,
        )
        width = max(canvas.winfo_width(), 1200)
        height = max(canvas.winfo_height(), 650)
        left = 310
        top = 58
        right_margin = 10
        cell_width = (width - left - right_margin) / (AST_MAX_STEP + 1)
        row_height = min(50, (height - top - 8) / max(len(players), 1))

        canvas.create_text(
            12,
            28,
            text="A.S.T. rank / Civilization (player)",
            anchor="w",
            fill=MUTED,
            font=("Segoe UI Semibold", 11),
        )
        for step in range(AST_MAX_STEP + 1):
            x = left + step * cell_width
            canvas.create_rectangle(
                x,
                6,
                x + cell_width,
                top,
                fill=PANEL_ALT if step else PANEL,
                outline="#46566e",
            )
            canvas.create_text(
                x + cell_width / 2,
                22,
                text=str(step * 5),
                fill=TEXT,
                font=("Segoe UI Semibold", 11),
            )
            canvas.create_text(
                x + cell_width / 2,
                42,
                text="VP",
                fill=MUTED,
                font=("Segoe UI", 8),
            )

        for row, player in enumerate(players):
            civilization = CIVILIZATION_BY_NAME[player.civilization]
            era_starts = basic_ast_era_starts(
                player.civilization,
                self.game.player_count,
                self.game.game_mode,
            )
            y = top + row * row_height
            canvas.create_rectangle(
                0,
                y,
                left,
                y + row_height,
                fill=civilization.color,
                outline="#46566e",
            )
            canvas.create_text(
                14,
                y + row_height / 2,
                text=f"{civilization.ast_rank:>2}.  {player.display_name}",
                anchor="w",
                fill=civilization.text_color,
                font=("Segoe UI Semibold", 12),
            )
            for step in range(AST_MAX_STEP + 1):
                x = left + step * cell_width
                current = step == player.ast_step
                era_index = ast_era_index(
                    player.civilization,
                    step,
                    self.game.ast_variant,
                    self.game.player_count,
                    self.game.game_mode,
                )
                fill = (
                    civilization.color
                    if current
                    else AST_ERA_COLORS[era_index]
                )
                era_boundary = (
                    step > 0
                    and step in era_starts
                )
                canvas.create_rectangle(
                    x,
                    y,
                    x + cell_width,
                    y + row_height,
                    fill=fill,
                    outline=ACCENT if era_boundary else "#46566e",
                    width=3 if era_boundary else 1,
                    tags=(f"ast_{row}_{step}",),
                )
                if current:
                    state = ast_marker_state(
                        player,
                        self.game.player_count,
                        self.game.game_mode,
                    )
                    marker_color, marker_symbol = AST_MARKER_STYLES[state]
                    radius = min(cell_width, row_height) * 0.33
                    center_x = x + cell_width / 2
                    center_y = y + row_height / 2
                    canvas.create_oval(
                        center_x - radius,
                        center_y - radius,
                        center_x + radius,
                        center_y + radius,
                        fill=marker_color,
                        outline="#ffffff",
                        width=1,
                        tags=(f"ast_{row}_{step}",),
                    )
                    canvas.create_text(
                        center_x,
                        center_y,
                        text=marker_symbol,
                        fill=(
                            "#101010" if state == "FINISHED" else "#ffffff"
                        ),
                        font=("Segoe UI Semibold", max(9, int(radius * 1.25))),
                        tags=(f"ast_{row}_{step}",),
                    )
                elif step in era_starts:
                    canvas.create_text(
                        x + 5,
                        y + 5,
                        text=AST_ERA_ABBREVIATIONS[era_index],
                        anchor="nw",
                        fill="#e2e8ef",
                        font=("Segoe UI Semibold", 7),
                        tags=(f"ast_{row}_{step}",),
                    )
                canvas.tag_bind(
                    f"ast_{row}_{step}",
                    "<Button-1>",
                    lambda _event, selected=player, selected_step=step: (
                        self._set_ast(selected, selected_step)
                    ),
                )

    def _set_ast(self, player: PlayerState, step: int) -> None:
        player.ast_step = step
        self._save_and_refresh()


def run() -> None:
    root = tk.Tk()
    MegaEmpiresApp(root)
    root.mainloop()
