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

from gcheck.app import GcheckApp
from gcheck.ui.screens.language import LangCard, LanguageScreen
from gcheck.ui.screens.trust import TrustScreen


async def test_first_card_selected_and_focused_on_mount():
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LanguageScreen)
        cards = list(screen.query(LangCard))
        assert [c.lang_code for c in cards] == ["en", "zh", "es", "ja"]
        assert cards[0].selected is True
        assert all(not c.selected for c in cards[1:])
        assert screen.focused is cards[0]


async def test_arrow_right_then_down_moves_selection_through_the_2x2_grid():
    # Layout order is [en, zh] / [es, ja]; right moves within the row, down
    # moves to the row below in the same column (see action_move's grid math).
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        cards = list(app.screen.query(LangCard))

        await pilot.press("right")
        assert cards[1].selected is True  # zh

        await pilot.press("down")
        assert cards[3].selected is True  # ja
        assert cards[1].selected is False


async def test_arrow_navigation_wraps_around_row_and_column():
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        cards = list(app.screen.query(LangCard))

        await pilot.press("left")  # wraps col 0 -> col 1 on the same row
        assert cards[1].selected is True

        await pilot.press("up")  # wraps row 0 -> row 1 on the same column
        assert cards[3].selected is True


async def test_enter_confirms_current_selection_and_advances_to_trust_screen():
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, TrustScreen)
        assert app.lang == "en"


async def test_clicking_a_card_selects_it_directly_and_advances():
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#card-zh")
        await pilot.pause()
        assert isinstance(app.screen, TrustScreen)
        assert app.lang == "zh"
