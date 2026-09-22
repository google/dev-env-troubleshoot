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

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Footer, Label, Static, TextArea
from textual import on, work

from ...api_diagnostic import gemini as api_gemini
from ...api_diagnostic import recommendations as api_recommendations
from ...api_diagnostic.models import ApiTestResult
from ...i18n import t
from ..theme import BLUE, ERROR_EMOJI, GREEN, RECOMMENDATION_EMOJI, RED, SUCCESS_EMOJI, WHITE
from ..widgets import AppHeader, _SPINNER_FRAMES, focus_primary_button

TROUBLESHOOTING_URL = "https://ai.google.dev/gemini-api/docs/troubleshooting"


class _ErrorBox(TextArea):
    """The raw-error TextArea -- arrow keys move the cursor/scroll within it
    as normal, but pressing further at a boundary (already on the first/last
    line, or at the very start/end of the text) escapes focus to the
    adjacent button instead of doing nothing. TextArea's own bindings
    otherwise capture all four arrow keys unconditionally, so without this
    override there'd be no way to arrow out of the box once focus lands on
    it -- only Tab would work."""

    def action_cursor_up(self, select: bool = False) -> None:
        if self.cursor_at_first_line:
            self.screen.focus_previous()
        else:
            super().action_cursor_up(select=select)

    def action_cursor_down(self, select: bool = False) -> None:
        if self.cursor_at_last_line:
            self.screen.focus_next()
        else:
            super().action_cursor_down(select=select)

    def action_cursor_left(self, select: bool = False) -> None:
        if self.cursor_at_start_of_text:
            self.screen.focus_previous()
        else:
            super().action_cursor_left(select=select)

    def action_cursor_right(self, select: bool = False) -> None:
        if self.cursor_at_end_of_text:
            self.screen.focus_next()
        else:
            super().action_cursor_right(select=select)


class ApiKeyTestScreen(Screen):
    """Step 6 — validate the chosen key against Google. Final step of the flow."""

    BINDINGS = [
        ("left",  "prev_button", "Previous"),
        ("right", "next_button", "Next"),
        ("up",    "prev_button", "Previous"),
        ("down",  "next_button", "Next"),
    ]

    # Plain focus_previous()/focus_next() (as every other screen uses) would
    # cycle through #api-test-error-box fine when moving *into* it -- the
    # box's own action_cursor_* overrides (see _ErrorBox above) handle
    # escaping back out at its boundaries. What plain focus_previous()/next()
    # can't do on its own is know to land on the *primary* button (not just
    # the first one in the chain, which would be the box) the very first
    # time an arrow key is pressed -- that initial pick has to match
    # app.py's on_key fallback, which this action runs alongside.
    def _buttons(self) -> list[Button]:
        return [b for b in self.query(Button) if b.display]

    def _nav_chain(self) -> list[Widget]:
        """Error box (if shown) + visible buttons, box first -- the full set
        of stops arrow-key travel cycles through, wrapping at both ends."""
        box = self.query_one("#api-test-error-box")
        chain: list[Widget] = [box] if box.display else []
        chain.extend(self._buttons())
        return chain

    def action_prev_button(self) -> None:
        self._advance_focus(-1)

    def action_next_button(self) -> None:
        self._advance_focus(1)

    def _advance_focus(self, step: int) -> None:
        chain = self._nav_chain()
        if not chain:
            return
        if self.focused in chain:
            target = chain[(chain.index(self.focused) + step) % len(chain)]
            if isinstance(target, TextArea):
                # Land at the end when arriving from below (step < 0, moving
                # "up"/"left" into the box), at the start otherwise -- so it
                # feels like a continuous line rather than jumping around.
                target.cursor_location = target.document.end if step < 0 else (0, 0)
            target.focus()
        else:
            buttons = self._buttons()
            if buttons:
                primary = next((b for b in buttons if b.has_class("-primary")), buttons[0])
                primary.focus()

    def __init__(self, api_key: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key

    def compose(self) -> ComposeResult:
        yield AppHeader(id="app-header")
        yield Container(
            Label(t("api_test_title"), id="api-test-title"),
            Static(f"{_SPINNER_FRAMES[0]} {t('api_test_running')}", id="api-test-status", classes="msg-thinking"),
            Container(
                Static("", id="api-test-summary"),
                Label(t("api_test_original_error_label"), id="api-test-error-label"),
                _ErrorBox("", id="api-test-error-box", read_only=True, soft_wrap=True),
                Static("", id="api-test-result-text"),
                Horizontal(
                    Button(t("action_quit"), variant="default", id="btn-test-quit"),
                    Button(t("action_retry"), variant="default", id="btn-test-recheck"),
                    Button(t("action_try_different_key"), variant="primary", id="btn-test-retry"),
                    id="api-test-buttons",
                ),
                id="api-test-result",
            ),
            id="api-test-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#api-test-result").display = False
        self._start_spinner(t("api_test_running"))
        self._run_test()

    def _start_spinner(self, text: str) -> None:
        """(Re)start the loading spinner with a given caption. Also used by the
        Retry button, which re-runs the test after _on_result_inner has already
        stopped the timer and hidden the status line."""
        self._status_text = text
        self._spinner_index = 0
        status = self.query_one("#api-test-status", Static)
        status.display = True
        status.update(f"{_SPINNER_FRAMES[0]} {text}")
        self._spinner_timer = self.set_interval(0.08, self._tick_spinner)

    def _tick_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_index]
        self.query_one("#api-test-status", Static).update(f"{frame} {self._status_text}")

    def _set_status(self, text: str) -> None:
        self._status_text = text

    @work(thread=True)
    def _run_test(self) -> None:
        # Any exception escaping the worker body would leave the spinner
        # running forever and the result box hidden (or crash the app via
        # Textual's exit_on_error). Turn it into a normal failed result so the
        # existing error + "Try a different key" UI renders instead.
        try:
            self._run_test_inner()
        except BaseException as exc:  # noqa: BLE001
            result = ApiTestResult(
                ok=False,
                stage="internal",
                error_status="INTERNAL_ERROR",
                message=f"{type(exc).__name__}: {exc}",
            )
            self.app.call_from_thread(self._on_result, result, "")

    def _run_test_inner(self) -> None:
        # Listing models only proves the key authenticates -- it's a metadata
        # call that Google doesn't gate behind billing/quota, so a free-tier
        # key with no billing enabled sails through it and only fails later,
        # on the first real chat message. Actually calling generateContent
        # here (like `python -m api_diagnostic` already does) exercises the
        # same billing/quota-gated path chat will use, so those failures show
        # up now, with a real diagnosis, instead of as a raw error in chat.
        listed = api_gemini.list_models(self._api_key)
        if not listed.ok:
            self.app.call_from_thread(self._on_result, listed, "")
            return

        model = api_gemini.pick_generate_model(listed)
        if not model:
            self.app.call_from_thread(self._on_result, listed, "")
            return

        self.app.call_from_thread(self._set_status, t("api_test_generating"))
        # Ask in whichever language is currently selected, so a Chinese user
        # sees the model actually reply in Chinese here rather than English.
        prompt = t("api_test_prompt")
        generated = api_gemini.generate(self._api_key, model, timeout=api_gemini.DEFAULT_TIMEOUT, prompt=prompt)
        reply = api_gemini.reply_text(generated) if generated.ok else ""
        self.app.call_from_thread(self._on_result, generated, reply)

    def _on_result(self, result: ApiTestResult, reply: str = "") -> None:
        # Runs on the UI thread (via call_from_thread). _on_result_inner does
        # a lot of i18n formatting and calls into api_recommendations.recommend()
        # -- anything raising there would propagate out of the event loop and
        # crash the app (Textual's exit_on_error) with the spinner still up and
        # the result box hidden. Fall back to a bare, can't-fail error render.
        try:
            self._on_result_inner(result, reply)
        except BaseException as exc:  # noqa: BLE001
            self._render_fatal(exc)

    def _render_fatal(self, exc: BaseException) -> None:
        try:
            self._spinner_timer.stop()
        except BaseException:  # noqa: BLE001
            pass
        try:
            self.query_one("#api-test-status").display = False
        except BaseException:  # noqa: BLE001
            pass
        try:
            try:
                heading = t("api_test_failed_heading", stage=t("api_test_stage_internal"))
            except BaseException:  # noqa: BLE001
                heading = "The API key test could not be completed."
            detail = f"{type(exc).__name__}: {exc}"
            self.query_one("#api-test-summary", Static).update(
                f"[{RED}]{ERROR_EMOJI} {escape(heading)}[/{RED}]\n"
                f"[{WHITE}]{escape(detail)}[/{WHITE}]"
            )
        except BaseException:  # noqa: BLE001
            pass
        for step in (
            lambda: setattr(self.query_one("#api-test-result"), "display", True),
            lambda: setattr(self.query_one("#btn-test-recheck", Button), "display", True),
            lambda: setattr(self.query_one("#btn-test-retry", Button), "display", True),
            lambda: focus_primary_button(self),
        ):
            try:
                step()
            except BaseException:  # noqa: BLE001
                pass

    def _on_result_inner(self, result: ApiTestResult, reply: str = "") -> None:
        self._spinner_timer.stop()
        self.query_one("#api-test-status").display = False

        summary = self.query_one("#api-test-summary", Static)
        error_label = self.query_one("#api-test-error-label", Label)
        error_box = self.query_one("#api-test-error-box", TextArea)
        text = self.query_one("#api-test-result-text", Static)
        retry_btn = self.query_one("#btn-test-retry", Button)

        error_label.display = False
        error_box.display = False

        if result.ok:
            lines = [f"[{GREEN}]{SUCCESS_EMOJI} {escape(t('api_test_success'))}[/{GREEN}]"]
            if result.stage == "generate":
                shown = reply or t("api_test_empty_reply")
                lines += ["", f"[{WHITE}]{escape(t('api_test_reply_label'))} {escape(shown)}[/{WHITE}]"]
                if not reply:
                    reason = api_gemini.block_reason(result)
                    if reason:
                        lines.append(f"[{RED}]{escape(t('api_test_blocked_reason', reason=reason))}[/{RED}]")
                        tip = api_recommendations.block_reason_tip(reason)
                        lines.append(f"[{WHITE}]{escape(tip)}[/{WHITE}]")
            else:
                lines += ["", f"[{WHITE}]{escape(t('api_test_no_generate_model'))}[/{WHITE}]"]
            summary.update("\n".join(lines))
            text.update("")
            retry_btn.display = False
            # A re-test of a key that just passed is pointless -- drop the Retry
            # button too, so only the quit/exit button remains; left-align it
            # rather than leaving a single button stranded at the far right edge.
            self.query_one("#btn-test-recheck", Button).display = False
            self.query_one("#api-test-buttons").add_class("-left")
        else:
            stage_label = {
                "list_models": t("api_test_stage_list_models"),
                "generate": t("api_test_stage_generate"),
                "internal": t("api_test_stage_internal"),
            }
            where = stage_label.get(result.stage, result.stage)
            summary_lines = [f"[{RED}]{ERROR_EMOJI} {escape(t('api_test_failed_heading', stage=where))}[/{RED}]"]

            details = []
            if result.http_status is not None:
                details.append(f"HTTP {result.http_status}")
            if result.error_status:
                details.append(result.error_status)
            if result.error_code:
                details.append(result.error_code)
            if details:
                summary_lines.append(f"  [{RED}]{escape(' · '.join(details))}[/{RED}]")
            summary.update("\n".join(summary_lines))

            # The exact, unmodified message Google sent back -- in its own
            # scrollable, read-only, focusable box so a long message doesn't
            # blow out the layout, and so it can be selected/copied as-is
            # rather than only read secondhand through our recommendation.
            error_box.text = result.message or t("api_test_no_raw_message")
            error_label.display = True
            error_box.display = True

            title, steps = api_recommendations.recommend(result)
            lines = [
                f"[bold {BLUE}]{RECOMMENDATION_EMOJI} {escape(t('api_test_recommended_fix', title=title))}[/bold {BLUE}]"
            ]
            lines.extend(f"  [{WHITE}]{escape(step)}[/{WHITE}]" for step in steps)

            # After a few failed attempts, the curated per-error recommendation
            # may just not cover it -- point at Google's own troubleshooting
            # docs (indexed by Gemini error code) as a fallback.
            self.app.api_test_fail_count += 1
            if self.app.api_test_fail_count >= 3:
                lines.append("")
                hint = escape(t("api_test_troubleshooting_hint", url=TROUBLESHOOTING_URL))
                lines.append(f"  [italic {WHITE}]{hint}[/italic {WHITE}]")

            text.update("\n".join(lines))

        self.query_one("#api-test-result").display = True

        # The buttons live inside #api-test-result, which is hidden until now
        # -- too late for the screen's AUTO_FOCUS at mount -- so focus the
        # primary action once it's visible: "Try a different key" on failure,
        # the quit button on success (nothing else is left).
        focus_primary_button(self)

    @on(Button.Pressed, "#btn-test-recheck")
    def on_recheck(self) -> None:
        # Re-run the test against the same key, without leaving the screen --
        # the fix for a transient Google-side error (500/503/timeout).
        self.query_one("#api-test-result").display = False
        self.query_one("#api-test-buttons").remove_class("-left")
        self.query_one("#api-test-error-label").display = False
        self.query_one("#api-test-error-box").display = False
        self._start_spinner(t("api_test_running"))
        self._run_test()

    @on(Button.Pressed, "#btn-test-retry")
    def on_retry(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-test-quit")
    def on_quit(self) -> None:
        self.app.exit()
