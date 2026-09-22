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

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Label
from textual import on

from ...i18n import t
from ..widgets import AppHeader


class TrustScreen(Screen):
    """Step 2 — folder trust confirmation."""

    # The only focusable widgets are the two buttons, side by side, so
    # Left/Right moves between them and Up/Down is freed up to scroll the
    # page (via #trust-container, which is the overflow-y: auto element).
    BINDINGS = [
        ("left",  "prev_button", "Previous"),
        ("right", "next_button", "Next"),
        Binding("up",   "scroll_up",   "Scroll up",   show=False),
        Binding("down", "scroll_down", "Scroll down", show=False),
    ]

    def action_prev_button(self) -> None:
        self.focus_previous()

    def action_next_button(self) -> None:
        self.focus_next()

    def action_scroll_up(self) -> None:
        self.query_one("#trust-container").scroll_up()

    def action_scroll_down(self) -> None:
        self.query_one("#trust-container").scroll_down()

    def compose(self) -> ComposeResult:
        cwd = os.getcwd()
        yield AppHeader(id="app-header")
        yield Container(
            Label(t("trust_prompt"), id="trust-title"),
            Label(f"{t('trust_folder_label')} {cwd}", id="trust-cwd"),
            Horizontal(
                Button(t("trust_no"), classes="btn-secondary", id="btn-deny"),
                Button(t("trust_yes"), variant="primary", id="btn-allow"),
                id="trust-buttons",
            ),
            id="trust-container",
        )
        yield Footer()

    @on(Button.Pressed, "#btn-allow")
    def on_allow(self) -> None:
        from .diagnostic import DiagnosticScreen

        self.app.push_screen(DiagnosticScreen())

    @on(Button.Pressed, "#btn-deny")
    def on_deny(self) -> None:
        self.app.exit(message=t("trust_denied"))
