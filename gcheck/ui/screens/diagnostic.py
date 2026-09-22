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
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Static
from textual import on, work

from ...diagnostics import (
    GOOGLE_TARGET_DOMAIN,
    check_gateway,
    check_general_baseline,
    check_google_reachability,
    check_network_info,
)
from ...gate import check_gate
from ...i18n import t
from ...network_check.models import CheckResult
from ...recommendations import build_diagnosis
from ..theme import BLUE, RECOMMENDATION_EMOJI
from ..widgets import (
    AppHeader,
    _SPINNER_FRAMES,
    _google_ok_line,
    _info_block,
    _tier_line,
    _tiers_all_ok_line,
    focus_primary_button,
)


class DiagnosticScreen(Screen):
    """Step 3 — gate check → collapsed per-tier pass/fail summary → diagnosis."""

    # The report's only focusable widgets are the buttons in one row, so
    # Left/Right moves between them and Up/Down is freed up to scroll the
    # report (via #diag-container, the overflow-y: auto element) -- which
    # matters here because the diagnosis can run past a short terminal.
    BINDINGS = [
        ("left",  "prev_button", "Previous"),
        ("right", "next_button", "Next"),
        Binding("up",   "scroll_up",   "Scroll up",   show=False),
        Binding("down", "scroll_down", "Scroll down", show=False),
    ]

    # keys that must all be present in self._results before the diagnosis can render
    _REQUIRED = {"network_info", "gateway", "baseline", "google"}

    def action_prev_button(self) -> None:
        self.focus_previous()

    def action_next_button(self) -> None:
        self.focus_next()

    def action_scroll_up(self) -> None:
        self.query_one("#diag-container").scroll_up()

    def action_scroll_down(self) -> None:
        self.query_one("#diag-container").scroll_down()

    def compose(self) -> ComposeResult:
        yield AppHeader(id="app-header")
        yield Vertical(
            Static(t("checking_connection"), id="diag-loading-header", classes="diag-loading-header"),
            Static(f"{_SPINNER_FRAMES[0]} {t('running_diagnostics')}", id="diag-loading-status", classes="msg-thinking"),
            Static("", id="diag-network"),
            Static("", id="diag-tiers"),
            Static("", id="diag-diagnosis"),
            Static("", id="diag-recommendations"),
            Horizontal(
                Button(t("action_quit"), variant="default", id="btn-quit"),
                Button(t("action_check_again"), classes="btn-secondary", id="btn-again"),
                Button(t("action_next"), variant="primary", id="btn-chat"),
                id="diag-buttons",
            ),
            id="diag-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._start_check()

    def _start_check(self) -> None:
        self._reset_diag_state()
        # The gate check (and, if offline, the three checks it triggers) all
        # run in background workers -- without this, the screen sits blank
        # until the first result lands, which reads as frozen rather than
        # "in progress". The "Checking Google connection" header stays up
        # for the whole page; the spinner/status line below it is
        # (re)started here and stopped once all three checks have landed (see
        # _stop_loading_status, called from _finalize) -- "Check again"
        # reuses this same screen instance instead of remounting it, so
        # both need resetting.
        status = self.query_one("#diag-loading-status", Static)
        status.display = True
        self._spinner_index = 0
        status.update(f"{_SPINNER_FRAMES[0]} {t('running_diagnostics')}")
        if getattr(self, "_spinner_timer", None) is not None:
            self._spinner_timer.stop()
        self._spinner_timer = self.set_interval(0.08, self._tick_spinner)
        self._run_gate_check()

    def _tick_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_index]
        self.query_one("#diag-loading-status", Static).update(f"{frame} {t('running_diagnostics')}")

    def _stop_loading_status(self) -> None:
        if getattr(self, "_spinner_timer", None) is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.query_one("#diag-loading-status", Static).display = False

    # The three tiers are computed concurrently (see _launch_checks) and can
    # land in any order -- results are buffered in _tier_results and only
    # rendered once all three are in, so the tier box can decide up front
    # whether to show the failing tiers or a single all-clear line.
    _TIER_ORDER = ["gateway", "baseline", "google"]

    def _reset_diag_state(self) -> None:
        self._results: dict = {}
        self._reachable = False
        self._tier_results: dict = {}
        self._network_section_emitted = False
        self._check_failed = False
        for widget_id in ("diag-network", "diag-tiers", "diag-diagnosis", "diag-recommendations"):
            widget = self.query_one(f"#{widget_id}", Static)
            widget.update("")
            widget.display = False
        self.query_one("#diag-buttons").display = False

    def _record_tier(self, key: str, title: str, ok: bool) -> None:
        self._tier_results[key] = (title, ok)
        if len(self._tier_results) < len(self._TIER_ORDER):
            return

        widget = self.query_one("#diag-tiers", Static)

        # This diagnostic exists to answer "can I reach Google" -- if Tier 2
        # passes, a lower tier failing alongside it isn't a real problem for
        # that question, so it's not worth surfacing as an error here.
        if self._tier_results["google"][1]:
            widget.update(_google_ok_line())
            widget.display = True
            return

        failures = [
            _tier_line(title, False)
            for title, ok in (self._tier_results[k] for k in self._TIER_ORDER)
            if not ok
        ]
        widget.update("\n\n".join(failures) if failures else _tiers_all_ok_line())
        widget.display = True

    @work(thread=True)
    def _run_gate_check(self) -> None:
        try:
            reachable = check_gate()
        except BaseException as exc:  # noqa: BLE001 -- see _on_check_error
            self.app.call_from_thread(self._on_check_error, exc)
            return
        self.app.call_from_thread(self._dispatch, self._on_gate_result, reachable)

    def _on_gate_result(self, reachable: bool) -> None:
        # Always run the full diagnostic transcript, even when the gate check
        # succeeds -- a fast/unblocked connection used to skip straight to
        # the next step, which meant there was nothing to look at for users
        # who aren't behind a firewall. They get a "Next" button in
        # _finalize() instead of being auto-routed.
        self._reachable = reachable
        self._launch_checks()

    # ── three checks, launched together and computed in parallel, but their
    #    tier results are only rendered once all three are in (see
    #    _TIER_ORDER / _record_tier) regardless of completion order ──

    def _launch_checks(self) -> None:
        self._results = {}
        self._run_gateway_check()
        self._run_baseline_check()
        self._run_google_check()

    @work(thread=True)
    def _run_gateway_check(self) -> None:
        try:
            info = check_network_info()
            gateway = check_gateway(info.get("gateway") or "", info.get("is_tunnel", False))
        except BaseException as exc:  # noqa: BLE001 -- see _on_check_error
            self.app.call_from_thread(self._on_check_error, exc)
            return
        self.app.call_from_thread(self._dispatch, self._on_gateway_result, info, gateway)

    def _on_gateway_result(self, info: dict, gateway: CheckResult) -> None:
        self._record("network_info", info)
        self._record("gateway", gateway)
        self._maybe_emit_network_section()

    @work(thread=True)
    def _run_baseline_check(self) -> None:
        try:
            results = check_general_baseline()
        except BaseException as exc:  # noqa: BLE001 -- see _on_check_error
            self.app.call_from_thread(self._on_check_error, exc)
            return
        self.app.call_from_thread(self._dispatch, self._on_baseline_result, results)

    def _on_baseline_result(self, results: list[CheckResult]) -> None:
        ok = all(c.ok for c in results)
        self._record_tier("baseline", t("diag_tier1_title"), ok)
        self._record("baseline", results)

    @work(thread=True)
    def _run_google_check(self) -> None:
        try:
            results = check_google_reachability()
        except BaseException as exc:  # noqa: BLE001 -- see _on_check_error
            self.app.call_from_thread(self._on_check_error, exc)
            return
        self.app.call_from_thread(self._dispatch, self._on_google_result, results)

    def _on_google_result(self, results: list[CheckResult]) -> None:
        ok = all(r.ok for r in results)
        self._record_tier("google", t("diag_tier2_title", domain=GOOGLE_TARGET_DOMAIN), ok)
        self._record("google", results)

    def _maybe_emit_network_section(self) -> None:
        if self._network_section_emitted:
            return
        if not {"network_info", "gateway"}.issubset(self._results):
            return
        self._network_section_emitted = True

        info = self._results["network_info"]
        gateway = self._results["gateway"]

        unknown = t("diag_unknown")
        connection_type = info["connection_type"]
        if connection_type == "unknown":
            connection_type = unknown
        if not info["gateway"] and info.get("is_tunnel"):
            gateway_display = t("diag_gateway_tunnel_na")
        else:
            gateway_display = info["gateway"] or unknown

        net_lines = [
            f"  {t('diag_platform')}: {info['platform']}",
            f"  {t('diag_interface')}: {info['interface'] or unknown}",
            f"  {t('diag_connection_type')}: {connection_type}",
            f"  {t('diag_local_ip')}: {info['local_ip'] or unknown}",
            f"  {t('diag_gateway')}: {gateway_display}",
            f"  {t('diag_dns_servers')}: {', '.join(info['dns_servers']) or unknown}",
        ]
        network_widget = self.query_one("#diag-network", Static)
        network_widget.update(_info_block(t("diag_section_network"), net_lines))
        network_widget.display = True

        self._record_tier("gateway", t("diag_tier0_title"), gateway.ok)

    # ── finalize once all three are in ─────────────────────────────────────────

    def _record(self, key: str, value) -> None:
        self._results[key] = value
        if self._REQUIRED.issubset(self._results):
            self._finalize()

    def _finalize(self) -> None:
        # Runs on the UI thread (via _record <- call_from_thread). Anything
        # raising in here -- a malformed result reaching build_diagnosis, say
        # -- would otherwise propagate out and take the whole app down, so
        # funnel it into the same graceful failure path as a worker crash.
        try:
            self._finalize_inner()
        except Exception as exc:  # noqa: BLE001 -- see _on_check_error
            self._on_check_error(exc)

    def _finalize_inner(self) -> None:
        self._stop_loading_status()
        r = self._results

        # The gate check (see _on_gate_result) is a bare TCP connect -- it
        # can't see a real DNS+HTTPS failure against this exact host. The
        # Google reachability check for this same domain just ran, so it
        # supersedes the gate's guess as the authoritative answer for
        # whether "Next" should actually appear.
        target_result = next((g for g in r["google"] if g.name == GOOGLE_TARGET_DOMAIN), None)
        self._reachable = bool(target_result and target_result.ok)

        diag = build_diagnosis(r["network_info"], r["gateway"], r["baseline"], r["google"])
        diagnosis_widget = self.query_one("#diag-diagnosis", Static)
        diagnosis_widget.update(_info_block(t("diag_diagnosis_title"), [f"  {diag['diagnosis']}"]))
        diagnosis_widget.display = True

        if diag["recommendations"]:
            rec_widget = self.query_one("#diag-recommendations", Static)
            rec_widget.update(
                _info_block(
                    t("diag_recommendations_title"),
                    [f"  {i}. {rec}" for i, rec in enumerate(diag["recommendations"], 1)],
                    color=BLUE,
                    emoji=RECOMMENDATION_EMOJI,
                )
            )
            rec_widget.display = True

        chat_btn = self.query_one("#btn-chat", Button)
        chat_btn.display = self._reachable
        self.query_one("#diag-buttons").display = True

        # The primary "Next" button (#btn-chat) only exists in the tree once
        # checks land -- too late for the screen's AUTO_FOCUS, which ran at
        # mount -- so focus it here. When the target is unreachable it's
        # hidden and this falls back to the first visible button (Quit).
        focus_primary_button(self)

    def _dispatch(self, fn, *args) -> None:
        # Every worker hands its successful result back to the UI thread
        # through here. The result handlers (_on_*_result -> _record /
        # _record_tier / _maybe_emit_network_section) index into the worker
        # payloads and call i18n -- a malformed payload raising there would
        # propagate straight out of the event loop and take the app down
        # (Textual re-raises unhandled callback exceptions), bypassing the
        # graceful failure screen. Route those into the same path as a worker
        # that crashed outright. (_finalize has its own inner guard, so a
        # failure in the diagnosis render is handled before it reaches here.)
        try:
            fn(*args)
        except BaseException as exc:  # noqa: BLE001 -- see _on_check_error
            self._on_check_error(exc)

    def _on_check_error(self, exc: BaseException) -> None:
        # A background check raised instead of returning a result (or
        # _finalize / a result handler itself failed). Without this, the
        # _record() barrier never completes, _finalize() never runs, and the
        # spinner spins forever with no buttons -- the user is locked out of
        # the wizard. Stop the spinner, say what happened, and leave working
        # Quit / Check again buttons. Guarded so only the first of several
        # failing workers wins.
        if getattr(self, "_check_failed", False):
            return
        self._check_failed = True
        try:
            self._render_check_error(exc)
        except BaseException:  # noqa: BLE001
            # The failure screen itself failed to render (a widget missing, a
            # bad i18n key). Last resort: freeze the spinner and force *some*
            # working button on screen so the user isn't trapped.
            self._render_fatal_fallback()

    def _render_fatal_fallback(self) -> None:
        for step in (
            self._stop_loading_status,
            lambda: setattr(self.query_one("#btn-chat", Button), "display", False),
            lambda: setattr(self.query_one("#diag-buttons"), "display", True),
            lambda: focus_primary_button(self),
        ):
            try:
                step()
            except BaseException:  # noqa: BLE001
                pass

    def _render_check_error(self, exc: BaseException) -> None:
        self._stop_loading_status()

        diagnosis_widget = self.query_one("#diag-diagnosis", Static)
        diagnosis_widget.update(
            _info_block(
                t("diag_check_failed_title"),
                [f"  {t('diag_check_failed_body', error=type(exc).__name__)}"],
            )
        )
        diagnosis_widget.display = True

        rec_widget = self.query_one("#diag-recommendations", Static)
        rec_widget.update(
            _info_block(
                t("diag_recommendations_title"),
                [f"  1. {t('diag_check_failed_rec')}"],
                color=BLUE,
                emoji=RECOMMENDATION_EMOJI,
            )
        )
        rec_widget.display = True

        self.query_one("#btn-chat", Button).display = False
        self.query_one("#diag-buttons").display = True
        focus_primary_button(self)

    @on(Button.Pressed, "#btn-again")
    def on_check_again(self) -> None:
        self._start_check()

    @on(Button.Pressed, "#btn-chat")
    def on_go_to_chat(self) -> None:
        from .api_finding import ApiFindingScreen

        self.app.push_screen(ApiFindingScreen())

    @on(Button.Pressed, "#btn-quit")
    def on_quit_pressed(self) -> None:
        self.app.exit()
