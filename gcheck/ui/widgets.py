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
from textual.containers import Horizontal
from textual.widgets import Button, Label, Static

from ..i18n import t
from .theme import DIAGNOSTIC_EMOJI, ERROR_EMOJI, GREEN, RED, SUCCESS_EMOJI, WHITE, YELLOW

# ─── Diagnostic result formatting helpers ──────────────────────────────────────
# Section titles and the diagnosis/recommendation narrative are translated via
# gcheck's i18n system (see gcheck/locales/*.json, keys prefixed "diag_"). Rendered as
# Rich markup on Static widgets, matching the API key test screen's look
# (colored pass/fail headline + dim detail) rather than the plain-text CLI
# transcript style network_check/cli.py uses.

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _icon(ok: bool) -> str:
    # return "✅" if ok else "❌"
    return "" if ok else ""



def _tier_line(title: str, ok: bool) -> str:
    """One collapsed, colored headline per tier; subtest/error detail is hidden."""
    color = GREEN if ok else RED
    emoji = SUCCESS_EMOJI if ok else ERROR_EMOJI
    status = t("diag_status_ok") if ok else t("diag_status_failed")
    return f"[{color}]{emoji} {_icon(ok)} {escape(title)} — {status}[/{color}]"


def _tiers_all_ok_line() -> str:
    """Single success line shown in place of a per-tier list when nothing failed."""
    return f"[{GREEN}]{SUCCESS_EMOJI} {_icon(True)} {escape(t('diag_tiers_all_ok'))}[/{GREEN}]"


def _google_ok_line() -> str:
    """Shown whenever Tier 2 (Google) passes, regardless of Tiers 0-1 -- this
    diagnostic exists to answer "can I reach Google", not "is the network
    perfect", so a lower tier failing alongside a working Google connection
    isn't worth surfacing as an error."""
    return f"[{GREEN}]{SUCCESS_EMOJI} {_icon(True)} {escape(t('diag_google_ok'))}[/{GREEN}]"


def _info_block(
    title: str,
    lines: list[str],
    *,
    color: str = YELLOW,
    body_color: str = WHITE,
    emoji: str = DIAGNOSTIC_EMOJI,
) -> str:
    """A zone: heading in `color`, body lines in `body_color`."""
    heading = f"[bold {color}]{emoji} {escape(title)}[/bold {color}]"
    body = "\n".join(f"[{body_color}]{escape(line)}[/{body_color}]" for line in lines)
    return heading + "\n" + body


def _mask_key(value: str) -> str:
    """Mask a secret for display: ``AIzaSy…w1YQ``."""
    if not value:
        return ""
    if len(value) <= 10:
        return "…" + value[-2:]
    return f"{value[:6]}…{value[-4:]}"


# ─── Shared components ────────────────────────────────────────────────────────

def focus_primary_button(screen) -> bool:
    """Focus the screen's primary (``variant="primary"``) button so the
    wizard's "advance" action is the pre-selected default -- Enter works
    without pressing Tab/arrows first. Falls back to the first visible
    button. Buttons that are hidden (``display: none`` or inside a hidden
    container) are skipped, since ``focus_chain`` already excludes them.
    Returns True if a button was focused.

    Mirrors the arrow-key fallback in app.py's ``on_key`` / the API test
    screen's ``_advance_focus`` -- screens whose primary button only appears
    after async work call this once it's shown, rather than at mount."""
    buttons = [w for w in screen.focus_chain if isinstance(w, Button)]
    if not buttons:
        return False
    primary = next((b for b in buttons if b.has_class("-primary")), buttons[0])
    primary.focus()
    return True


class AppHeader(Horizontal):
    """Title bar with the app name."""

    def compose(self) -> ComposeResult:
        yield Label(t("app_name"), id="header-title")
