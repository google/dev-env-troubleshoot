# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Label, Static

from ...i18n import t
from ..widgets import AppHeader
from .trust import TrustScreen


class LangCard(Static, can_focus=True):
    """Selectable language card — focusable, navigable with arrow keys.
    There's no separate Continue button: clicking a card (or pressing Enter
    while it's focused) picks that language and moves on to the next step."""

    selected: reactive[bool] = reactive(False)

    def __init__(self, lang_code: str, label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lang_code = lang_code
        self._label = label

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="lang-card-label")

    def watch_selected(self, value: bool) -> None:
        self.set_class(value, "selected")

    def on_click(self) -> None:
        self.screen.choose(self)


class LanguageScreen(Screen):
    """Step 1 — pick a language. Choosing a card (click or Enter) is what
    advances; there is no separate Continue button."""

    # Cards are laid out as a 2x2 grid (see #lang-cards in app.tcss) --
    # left/right move within a row, up/down move between rows.
    _GRID_COLS = 2

    BINDINGS = [
        ("left",  "move(-1, 0)", "Previous"),
        ("right", "move(1, 0)",  "Next"),
        ("up",    "move(0, -1)", "Up"),
        ("down",  "move(0, 1)",  "Down"),
        ("enter", "confirm",     "Select"),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader(id="app-header")
        yield Container(
            Label(t("select_language"), id="lang-title"),
            Container(
                LangCard("en", t("lang_en"), id="card-en", classes="lang-card"),
                LangCard("zh", t("lang_zh"), id="card-zh", classes="lang-card"),
                LangCard("es", t("lang_es"), id="card-es", classes="lang-card"),
                LangCard("ja", t("lang_ja"), id="card-ja", classes="lang-card"),
                id="lang-cards",
            ),
            id="lang-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        cards = list(self.query(LangCard))
        cards[0].selected = True
        cards[0].focus()

    def action_move(self, dx: int, dy: int) -> None:
        cards = list(self.query(LangCard))
        cols = self._GRID_COLS
        rows = (len(cards) + cols - 1) // cols
        current = next((i for i, c in enumerate(cards) if c.selected), 0)
        row, col = divmod(current, cols)
        col = (col + dx) % cols
        row = (row + dy) % rows
        target = row * cols + col
        for card in cards:
            card.selected = False
        cards[target].selected = True
        cards[target].focus()

    def action_confirm(self) -> None:
        selected = next((c for c in self.query(LangCard) if c.selected), None)
        if selected is not None:
            self.choose(selected)

    def choose(self, card: LangCard) -> None:
        for c in self.query(LangCard):
            c.selected = False
        card.selected = True
        self.app.set_lang(card.lang_code)
        self.app.push_screen(TrustScreen())
