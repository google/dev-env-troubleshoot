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
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, RadioButton, RadioSet, Static
from textual import events, on, work

from ...api_diagnostic.models import FoundKey
from ...code_setup import find_api_keys
from ...i18n import t
from ..widgets import AppHeader, _SPINNER_FRAMES, _mask_key


class _KeyPicker(RadioSet):
    """The found-keys picker. A plain RadioSet wraps the highlight around at
    both ends, so the down arrow can never leave the list. Here, pressing
    down while on the last option (always "Enter key manually") moves focus
    to the manual-entry Input below instead -- the arrows walk straight from
    the list into the input rather than looping."""

    def action_next_button(self) -> None:
        if self._selected is not None and self._selected == len(self._nodes) - 1:
            self.screen.focus_next()
        else:
            super().action_next_button()


class ApiFindingScreen(Screen):
    """Step 5 — search for existing API key(s); confirm, pick, or replace one."""

    BINDINGS = [
        ("left",  "prev_button", "Previous"),
        ("right", "next_button", "Next"),
        ("up",    "prev_button", "Previous"),
        ("down",  "next_button", "Next"),
    ]

    def action_prev_button(self) -> None:
        self.focus_previous()

    def action_next_button(self) -> None:
        self.focus_next()

    def compose(self) -> ComposeResult:
        yield AppHeader(id="app-header")
        yield Container(
            Label(t("api_finding_title"), id="api-finding-title"),
            Label(t("api_finding_notice"), id="api-finding-notice"),
            Static(f"{_SPINNER_FRAMES[0]} {t('api_finding_running')}", id="api-finding-status", classes="msg-thinking"),
            Container(
                Label("", id="api-finding-message"),
                _KeyPicker(id="api-finding-picker"),
                Input(id="api-finding-input", placeholder=t("api_finding_input_placeholder")),
                Static(t("api_finding_token_notice"), id="api-finding-token-notice"),
                Horizontal(
                    Button(t("action_quit"), variant="default", id="btn-api-quit"),
                    Button(t("action_next"), variant="primary", id="btn-api-continue"),
                    id="api-finding-buttons",
                ),
                id="api-finding-result",
            ),
            id="api-finding-container",
        )
        yield Footer()

    # A directory scan can take a very long time on huge trees (e.g. running
    # from deep inside C:\Users) -- os.walk can't be safely interrupted
    # mid-traversal once started in the worker thread. So rather than block
    # the screen on it indefinitely, give up waiting after this long and let
    # the user type the key themselves instead.
    FINDER_TIMEOUT_SECONDS = 5.0

    def on_mount(self) -> None:
        self.query_one("#api-finding-result").display = False
        self.query_one("#api-finding-picker").display = False
        self._found_keys: list[FoundKey] = []
        self._current_key_value = ""
        self._finder_resolved = False
        self._spinner_index = 0
        self._spinner_timer = self.set_interval(0.08, self._tick_spinner)
        self._finder_timeout_timer = self.set_timer(self.FINDER_TIMEOUT_SECONDS, self._on_finder_timeout)
        self._run_finder()

    def _tick_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_index]
        self.query_one("#api-finding-status", Static).update(f"{frame} {t('api_finding_running')}")

    @work(thread=True)
    def _run_finder(self) -> None:
        try:
            keys = find_api_keys(os.getcwd())
        except BaseException:  # noqa: BLE001
            # A scan that raises (odd permissions, a path quirk) must not
            # leave the spinner up -- drop to the manual-entry path, same as
            # the timeout does.
            self.app.call_from_thread(self._resolve_without_keys, t("api_finding_scan_error"))
            return
        self.app.call_from_thread(self._on_find_result, keys)

    def _on_finder_timeout(self) -> None:
        # The scan itself keeps running in the background thread (it can't be
        # cancelled mid-walk) -- its result is simply ignored now, via the
        # _finder_resolved guard below, whenever it eventually lands.
        self._resolve_without_keys(t("api_finding_scan_timeout"))

    def _resolve_without_keys(self, message_text: str) -> None:
        """Shared exit for 'no usable scan result' -- timeout or scan error.
        Drops the spinner and hands the user the manual key input."""
        if self._finder_resolved:
            return
        self._finder_resolved = True
        self._finder_timeout_timer.stop()
        self._spinner_timer.stop()
        self.query_one("#api-finding-status").display = False

        message = self.query_one("#api-finding-message", Label)
        message.update(message_text)
        self.query_one("#api-finding-picker").display = False
        input_box = self.query_one("#api-finding-input", Input)
        self._current_key_value = ""
        input_box.value = ""
        input_box.focus()
        self.query_one("#api-finding-result").display = True

    def _on_find_result(self, keys: list[FoundKey]) -> None:
        # Runs on the UI thread. The render below mounts widgets and formats
        # i18n strings from scan output -- if any of that raises it would
        # propagate out of the event loop and crash the app, so on failure
        # fall through to the same manual-entry path the timeout/scan-error
        # uses. _finder_resolved is cleared first because _on_find_result_inner
        # sets it early; without the reset _resolve_without_keys would no-op.
        try:
            self._on_find_result_inner(keys)
        except BaseException:  # noqa: BLE001
            self._finder_resolved = False
            self._resolve_without_keys(t("api_finding_scan_error"))

    def _on_find_result_inner(self, keys: list[FoundKey]) -> None:
        if self._finder_resolved:
            return  # the timeout already fired; the user is entering a key manually now
        self._finder_resolved = True
        self._finder_timeout_timer.stop()
        self._spinner_timer.stop()
        self.query_one("#api-finding-status").display = False
        self._found_keys = keys

        message = self.query_one("#api-finding-message", Label)
        picker = self.query_one("#api-finding-picker", RadioSet)
        input_box = self.query_one("#api-finding-input", Input)
        picker.remove_children()

        if not keys:
            message.update(t("api_finding_not_found"))
            picker.display = False
            self._current_key_value = ""
            input_box.value = ""
            input_box.focus()
        elif len(keys) == 1:
            fk = keys[0]
            message.update(t(
                "api_finding_found",
                var_name=fk.var_name or t("api_finding_unnamed_key"),
                file=fk.file,
                line=fk.line,
            ))
            picker.display = False
            self._current_key_value = fk.value
            input_box.value = _mask_key(self._current_key_value)
            # Nothing is focused here -- DescendantFocus below reveals the
            # unmasked value on focus, which would defeat the mask before the
            # user has done anything, so the input isn't focused either.
        else:
            message.update(t("api_finding_found_multiple", count=len(keys)))
            radio_buttons = []
            for fk in keys:
                label = f"{fk.var_name or t('api_finding_unnamed_key')} — {fk.file}:{fk.line}  ({_mask_key(fk.value)})"
                rb = RadioButton(label)
                radio_buttons.append(rb)
                picker.mount(rb)
            picker.mount(RadioButton(t("api_finding_manual_option")))
            picker.display = True
            self._current_key_value = keys[0].value
            input_box.value = _mask_key(self._current_key_value)
            picker.focus()
            # RadioSet only reconciles "which button starts pressed" once, in its own
            # on_mount -- which runs immediately when the (still-empty) picker is first
            # composed, well before these buttons exist. Constructing a button with
            # value=True bypasses that bookkeeping entirely, so RadioSet's internal
            # _pressed_button stays None: the button still *looks* on, but RadioSet
            # doesn't know to turn it off when another one is pressed (two dots lit),
            # and clicking it again is a no-op (already True, so no Changed event
            # fires). Pressing it for real, after it has actually settled into the
            # DOM, is what makes RadioSet register it as the pressed button.
            self.call_after_refresh(self._press_first_key, radio_buttons[0])

        self.query_one("#api-finding-result").display = True

    def _press_first_key(self, button: RadioButton) -> None:
        button.value = True

    @on(RadioSet.Changed, "#api-finding-picker")
    def on_picker_changed(self, event: RadioSet.Changed) -> None:
        input_box = self.query_one("#api-finding-input", Input)
        if event.index is not None and event.index < len(self._found_keys):
            self._current_key_value = self._found_keys[event.index].value
            input_box.value = _mask_key(self._current_key_value)
        else:
            self._current_key_value = ""
            input_box.value = ""
            input_box.focus()

    # ── partial reveal while idle, full value while actively focused ──────────
    # The box shows the real, editable value only while it has focus (so you can
    # verify a paste or type a new key character-by-character); once it loses
    # focus, whatever it currently holds becomes the source of truth and is
    # redisplayed masked, so a bystander glancing at the screen doesn't see the
    # full secret at rest.

    @on(events.DescendantFocus, "#api-finding-input")
    def on_key_input_focus(self) -> None:
        self.query_one("#api-finding-input", Input).value = self._current_key_value

    @on(events.DescendantBlur, "#api-finding-input")
    def on_key_input_blur(self) -> None:
        input_box = self.query_one("#api-finding-input", Input)
        self._current_key_value = input_box.value
        input_box.value = _mask_key(self._current_key_value)

    @on(Button.Pressed, "#btn-api-continue")
    @on(Input.Submitted, "#api-finding-input")
    def on_continue(self) -> None:
        from .api_key_test import ApiKeyTestScreen

        input_box = self.query_one("#api-finding-input", Input)
        if input_box.has_focus:
            self._current_key_value = input_box.value
        value = self._current_key_value.strip()
        if not value:
            input_box.focus()
            return
        os.environ["GEMINI_API_KEY"] = value
        self.app.push_screen(ApiKeyTestScreen(value))

    @on(Button.Pressed, "#btn-api-quit")
    def on_quit(self) -> None:
        self.app.exit()
