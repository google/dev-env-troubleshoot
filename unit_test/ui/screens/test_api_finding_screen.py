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

import pytest
from textual.widgets import Label, RadioButton

from gcheck.api_diagnostic.models import FoundKey
from gcheck.app import GcheckApp
from gcheck.i18n import t
from gcheck.ui.screens.api_finding import ApiFindingScreen
from gcheck.ui.screens.api_key_test import ApiKeyTestScreen
from gcheck.ui.widgets import _mask_key

STANDARD_KEY = "AIza" + "a" * 35


@pytest.fixture(autouse=True)
def _restore_gemini_api_key_env(monkeypatch):
    # on_continue sets os.environ["GEMINI_API_KEY"] directly (not through
    # monkeypatch), so its automatic env teardown won't catch that -- restore
    # whatever was there (this repo's own .env may define one) by hand.
    original = os.environ.get("GEMINI_API_KEY")
    yield
    if original is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", original)


async def _push_finding_screen(app, pilot, found_keys, mocker):
    mocker.patch("gcheck.ui.screens.api_finding.find_api_keys", return_value=found_keys)
    screen = ApiFindingScreen()
    await app.push_screen(screen)
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
    return screen


async def test_no_keys_found_shows_manual_entry_focused(mocker):
    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, [], mocker)

        message = screen.query_one("#api-finding-message", Label)
        assert message.renderable == t("api_finding_not_found")
        assert screen.query_one("#api-finding-picker").display is False
        input_box = screen.query_one("#api-finding-input")
        assert input_box.value == ""
        assert screen.focused is input_box


async def test_single_key_found_prefills_masked_value(mocker):
    fk = FoundKey(value=STANDARD_KEY, file="app.py", line=3, var_name="GEMINI_API_KEY")

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, [fk], mocker)

        message = screen.query_one("#api-finding-message", Label)
        expected = t("api_finding_found", var_name="GEMINI_API_KEY", file="app.py", line=3)
        assert message.renderable == expected
        assert screen.query_one("#api-finding-picker").display is False
        assert screen._current_key_value == STANDARD_KEY
        assert screen.query_one("#api-finding-input").value == _mask_key(STANDARD_KEY)


async def test_single_key_found_with_no_var_name_uses_unnamed_label(mocker):
    fk = FoundKey(value=STANDARD_KEY, file="config.json", line=1, var_name=None)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, [fk], mocker)

        message = screen.query_one("#api-finding-message", Label)
        expected = t(
            "api_finding_found",
            var_name=t("api_finding_unnamed_key"),
            file="config.json",
            line=1,
        )
        assert message.renderable == expected


async def test_multiple_keys_shows_picker_with_manual_option_and_preselects_first(mocker):
    keys = [
        FoundKey(value=STANDARD_KEY, file="a.py", line=1, var_name="GEMINI_API_KEY"),
        FoundKey(value="AQ." + "b" * 25, file="b.py", line=2, var_name="GOOGLE_API_KEY"),
    ]

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, keys, mocker)
        # The first radio button's pressed state is set via
        # call_after_refresh -- give the extra refresh cycle a chance to run.
        await pilot.pause()

        message = screen.query_one("#api-finding-message", Label)
        assert message.renderable == t("api_finding_found_multiple", count=2)
        picker = screen.query_one("#api-finding-picker")
        assert picker.display is True

        radio_buttons = list(screen.query(RadioButton))
        assert len(radio_buttons) == 3  # 2 found keys + "enter manually"
        assert radio_buttons[0].value is True
        assert screen._current_key_value == keys[0].value


async def test_selecting_manual_option_in_picker_clears_current_value(mocker):
    keys = [
        FoundKey(value=STANDARD_KEY, file="a.py", line=1, var_name="GEMINI_API_KEY"),
        FoundKey(value="AQ." + "b" * 25, file="b.py", line=2, var_name="GOOGLE_API_KEY"),
    ]

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, keys, mocker)
        await pilot.pause()

        manual_option = list(screen.query(RadioButton))[-1]
        await pilot.click(manual_option)
        await pilot.pause()

        assert screen._current_key_value == ""
        assert screen.query_one("#api-finding-input").value == ""


async def test_continue_with_found_key_sets_env_and_advances(mocker):
    fk = FoundKey(value=STANDARD_KEY, file="app.py", line=3, var_name="GEMINI_API_KEY")

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, [fk], mocker)

        await pilot.click("#btn-api-continue")
        await pilot.pause()

        assert isinstance(app.screen, ApiKeyTestScreen)
        assert os.environ["GEMINI_API_KEY"] == STANDARD_KEY


async def test_continue_with_empty_value_focuses_input_and_stays(mocker):
    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, [], mocker)

        await pilot.click("#btn-api-continue")
        await pilot.pause()

        assert app.screen is screen
        assert screen.focused is screen.query_one("#api-finding-input")


async def test_quit_button_exits_app(mocker):
    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push_finding_screen(app, pilot, [], mocker)

        exit_spy = mocker.patch.object(app, "exit")
        await pilot.click("#btn-api-quit")
        await pilot.pause()
        exit_spy.assert_called_once()


async def test_finder_timeout_falls_back_to_manual_entry(mocker):
    # Invoking the internal timeout handler directly, rather than waiting
    # out the real FINDER_TIMEOUT_SECONDS, keeps this deterministic and fast.
    # The worker launch itself is stubbed out (not just find_api_keys) so the
    # scan can never race ahead and resolve on its own first -- mirrors the
    # real scenario this handles: a scan that's still walking a huge tree
    # when the timeout fires.
    mocker.patch("gcheck.ui.screens.api_finding.ApiFindingScreen._run_finder")
    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiFindingScreen()
        await app.push_screen(screen)
        await pilot.pause()

        screen._on_finder_timeout()
        await pilot.pause()

        message = screen.query_one("#api-finding-message", Label)
        assert message.renderable == t("api_finding_scan_timeout")
        assert screen.query_one("#api-finding-picker").display is False


async def test_scan_error_falls_back_to_manual_entry(mocker):
    mocker.patch(
        "gcheck.ui.screens.api_finding.find_api_keys", side_effect=PermissionError("nope")
    )
    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiFindingScreen()
        await app.push_screen(screen)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        message = screen.query_one("#api-finding-message", Label)
        assert message.renderable == t("api_finding_scan_error")
