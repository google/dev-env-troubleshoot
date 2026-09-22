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
from gcheck.ui.screens.language import LanguageScreen
from gcheck.ui.screens.trust import TrustScreen


async def test_app_boots_to_language_screen_by_default():
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LanguageScreen)


async def test_app_with_flag_lang_skips_straight_to_trust_screen():
    app = GcheckApp(flag_lang="es")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TrustScreen)
        assert app.lang == "es"


async def test_app_title_and_theme():
    app = GcheckApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.title == "gcheck"
        assert app.theme == "gcheck-dark"
