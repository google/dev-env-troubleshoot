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

import io
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import TerminalTheme
from textual import events
from textual.app import App
from textual.binding import Binding
from textual.widgets import Button, Input, TextArea

from .i18n import detect_language, set_language, t
from .ui.screens.language import LanguageScreen
from .ui.screens.trust import TrustScreen
from .ui.theme import BACKGROUND, GCHECK_DARK_THEME, WHITE
from .ui.widgets import _mask_key


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


# Textual apps put the terminal in a mode where mouse drags are captured for
# in-app widgets (e.g. TextArea selection) rather than becoming a native
# terminal selection, which means Ctrl+C can't fall back to the terminal's
# own copy handling -- it always reaches gcheck, which by default (like every
# Textual app) treats it as quit. Native clipboard tools sidestep that
# entirely, and are tried first because Textual's own OSC 52-based
# App.copy_to_clipboard() is documented to not work in stock macOS
# Terminal.app, only in more capable terminals (iTerm2, Windows Terminal).
def _copy_text_native(text: str) -> bool:
    if sys.platform == "darwin":
        cmd = ["pbcopy"]
    elif sys.platform == "win32":
        cmd = ["clip"]
    else:
        return False
    try:
        subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=2)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# Rich's SVG export renders against a generic dark-gray theme by default
# (background (41, 41, 41)), which doesn't quite match gcheck's actual
# background -- gives the exported card a faint mismatched border/backdrop.
# The 16 ANSI colors are copied from rich.console.SVG_EXPORT_THEME verbatim;
# only background/foreground are swapped to gcheck's real theme colors, since
# Textual widgets style with explicit truecolor rather than ANSI indices.
_SCREENSHOT_THEME = TerminalTheme(
    _hex_to_rgb(BACKGROUND),
    _hex_to_rgb(WHITE),
    [
        (75, 78, 85),
        (204, 85, 90),
        (152, 168, 75),
        (208, 179, 68),
        (96, 138, 177),
        (152, 114, 159),
        (104, 160, 179),
        (197, 200, 198),
        (154, 155, 153),
    ],
    [
        (255, 38, 39),
        (0, 130, 61),
        (208, 132, 66),
        (25, 132, 233),
        (255, 44, 122),
        (57, 130, 128),
        (253, 253, 197),
    ],
)

# Rich always draws a terminal-window "chrome" onto the exported SVG -- a
# title bar with three traffic-light dots -- baked into one opaque string
# with no public option to omit just that part. Passing title="" already
# drops the title text (see Console.export_svg), but the dots are
# unconditional, so they're cut from the rendered SVG afterward. The
# now-textless chrome background rect is left in place (colored to match
# gcheck's real background above, so it reads as a plain, borderless card
# rather than a labeled terminal tab).
_TRAFFIC_LIGHTS_RE = re.compile(r'<g transform="translate\(26,22\)">.*?</g>\s*', re.DOTALL)

# Some screens kick off blocking work (directory scans, network/API calls --
# see api_finding.py's os.walk and diagnostics.py's socket checks) on a
# background thread. Quitting while one of those is still in flight doesn't
# actually stop it -- Ctrl+C only interrupts the main thread, never a worker
# blocked in a syscall -- and both asyncio.run()'s own shutdown and Python's
# normal interpreter exit explicitly wait for every such thread to finish
# before the process is allowed to die. That can leave the terminal looking
# frozen for as long as that scan/request takes (up to the 15s API timeout).
# This grace period gives a normal, no-stuck-thread quit time to exit on its
# own; past it, we stop waiting and kill the process outright.
_FORCE_EXIT_GRACE_SECONDS = 1.5


class GcheckApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "gcheck"
    BINDINGS = [
        # A dedicated action, distinct from the ctrl+c-triggered action_quit
        # override below -- ctrl+q must always quit outright, even while a
        # copyable TextArea (error box / fix box) is focused.
        ("ctrl+q", "force_quit", "Quit"),
        # show=False: available via ctrl+s, but not worth a permanent Footer
        # slot for a niche, undiscoverable-by-design debug/support action.
        Binding("ctrl+s", "save_screenshot", "Save screenshot", show=False),
    ]
    # gcheck ships one fixed theme and its screens aren't meant to be
    # maximized/minimized, so Textual's default command palette (ctrl+p)
    # would only expose dead-end entries -- disable it outright.
    ENABLE_COMMAND_PALETTE = False
    # Auto-focus the primary (variant="primary") button on every screen that
    # has one visible at mount, so the wizard's "advance" action is the
    # pre-selected default and Enter works without pressing Tab/arrows first.
    # Textual only applies this when the screen hasn't already focused
    # something itself, so screens that focus their own control first
    # (LanguageScreen's card picker, the chat / API-key inputs) keep it, and
    # screens whose primary button appears only after async work (diagnostic,
    # API test) focus it via widgets.focus_primary_button once it's shown.
    AUTO_FOCUS = "Button.-primary"

    def __init__(self, flag_lang: str | None = None) -> None:
        super().__init__()
        self.register_theme(GCHECK_DARK_THEME)
        self.theme = "gcheck-dark"
        self.lang = detect_language(flag_lang)
        self.flag_lang = flag_lang
        self.api_test_fail_count = 0
        self._force_exit_armed = False
        set_language(self.lang)
        signal.signal(signal.SIGINT, self._on_sigint)

    def on_key(self, event: events.Key) -> None:
        if event.key not in ("up", "down", "left", "right"):
            return

        # First arrow key on a screen that hasn't focused anything yet (the
        # async diagnostic / API screens, before their buttons appear) lands
        # focus on the primary button so arrow navigation has a starting
        # point. Screens that focus their own control (LanguageScreen's
        # cards, the chat / API-key inputs) already have screen.focused set,
        # so this is a no-op there.
        if self.screen.focused is None:
            # Screen.focus_chain (not a raw query) is used here because it already
            # excludes hidden buttons -- both ones hidden directly (e.g. "Try
            # different key" on the API test success page) and ones hidden via an
            # ancestor (e.g. the whole diag-buttons row before checks land). A raw
            # query(Button) would still "find" and successfully focus those, since
            # Button.focusable only checks CSS visibility, not display.
            buttons = [w for w in self.screen.focus_chain if isinstance(w, Button)]
            if buttons:
                primary = next((b for b in buttons if b.has_class("-primary")), buttons[0])
                primary.focus()

    def _on_sigint(self, signum, frame) -> None:
        self._arm_force_exit()
        raise KeyboardInterrupt()

    def _arm_force_exit(self) -> None:
        if self._force_exit_armed:
            return
        self._force_exit_armed = True

        def _watchdog() -> None:
            time.sleep(_FORCE_EXIT_GRACE_SECONDS)
            os._exit(0)

        threading.Thread(target=_watchdog, daemon=True).start()

    def exit(self, *args, **kwargs) -> None:
        self._arm_force_exit()
        super().exit(*args, **kwargs)

    def action_force_quit(self) -> None:
        self.exit()

    # Overrides Textual's own App.action_quit, which is what its built-in
    # priority binding for ctrl+c calls (see BINDINGS above for ctrl+q's
    # separate, always-quit action). If a copyable box is focused, treat
    # ctrl+c as copy instead of quit -- see _copy_text_native's docstring for
    # why a real terminal selection can't just be left to handle this itself.
    def action_quit(self) -> None:
        focused = self.focused
        if isinstance(focused, TextArea):
            text = focused.selected_text or focused.text
            if text:
                self._copy_to_clipboard(text)
                return
        self.exit()

    def _copy_to_clipboard(self, text: str) -> None:
        if not _copy_text_native(text):
            self.copy_to_clipboard(text)
        self.notify(t("clipboard_copied"))

    def set_lang(self, lang: str) -> None:
        self.lang = lang
        set_language(lang)

    def on_mount(self) -> None:
        if self.flag_lang:
            self.push_screen(TrustScreen())
        else:
            self.push_screen(LanguageScreen())

    def _export_screenshot_svg(self) -> str:
        """Same approach as App.export_screenshot, but themed to match
        gcheck's real colors and with the terminal chrome's title/dots
        stripped -- see _SCREENSHOT_THEME / _TRAFFIC_LIGHTS_RE above."""
        assert self._driver is not None, "App must be running"
        width, height = self.size
        console = Console(
            width=width,
            height=height,
            file=io.StringIO(),
            force_terminal=True,
            color_system="truecolor",
            record=True,
            legacy_windows=False,
            safe_box=False,
        )
        # The API-key input shows its real value while focused (so a paste can
        # be eyeballed); at rest it's masked. A screenshot is a
        # share-with-support artifact, so redact any focused Input down to the
        # same partial mask for the capture, then restore it.
        restore = None
        focused = self.focused
        if isinstance(focused, Input) and focused.value:
            restore = (focused, focused.value)
            focused.value = _mask_key(focused.value)
        try:
            screen_render = self.screen._compositor.render_update(
                full=True, screen_stack=self._background_screens, simplify=False
            )
            console.print(screen_render)
        finally:
            if restore is not None:
                restore[0].value = restore[1]
        svg = console.export_svg(title="", theme=_SCREENSHOT_THEME)
        return _TRAFFIC_LIGHTS_RE.sub("", svg)

    def action_save_screenshot(self) -> None:
        svg = self._export_screenshot_svg()

        stem = f"{self.title} {datetime.now().isoformat()}"
        for reserved in ' <>:"/\\|?*.':
            stem = stem.replace(reserved, "_")
        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        path = downloads_dir / f"{stem}.svg"

        path.write_text(svg, encoding="utf-8")
        self.notify(f"Screenshot saved to {path}")
