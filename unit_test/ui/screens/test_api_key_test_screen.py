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

from textual.widgets import Button

from gcheck.api_diagnostic import recommendations as api_recommendations
from gcheck.api_diagnostic.models import ApiTestResult
from gcheck.app import GcheckApp
from gcheck.i18n import t
from gcheck.ui.screens.api_finding import ApiFindingScreen
from gcheck.ui.screens.api_key_test import TROUBLESHOOTING_URL, ApiKeyTestScreen


async def _push_and_wait(app, pilot, screen):
    """Push a screen whose on_mount fires a @work(thread=True) worker, and
    wait for both the worker thread and its call_from_thread callback to
    land on the UI thread before making assertions."""
    await app.push_screen(screen)
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def _flash_model(methods=("generateContent",)):
    return {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": list(methods)}


async def test_successful_generate_shows_reply_and_hides_retry_recheck(mocker):
    list_result = ApiTestResult(ok=True, stage="list_models", data={"models": [_flash_model()]})
    generate_result = ApiTestResult(
        ok=True,
        stage="generate",
        data={"candidates": [{"content": {"parts": [{"text": "Hi there!"}]}}]},
    )
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=list_result)
    mocker.patch("gcheck.api_diagnostic.gemini.generate", return_value=generate_result)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("fake-key")
        await _push_and_wait(app, pilot, screen)

        # On success, everything (the reply included) is written to
        # #api-test-summary -- #api-test-result-text is explicitly cleared.
        summary = str(screen.query_one("#api-test-summary").renderable)
        assert t("api_test_success") in summary
        assert "Hi there!" in summary
        assert str(screen.query_one("#api-test-result-text").renderable) == ""
        assert screen.query_one("#btn-test-retry", Button).display is False
        assert screen.query_one("#btn-test-recheck", Button).display is False


async def test_list_models_failure_shows_error_and_recommendation(mocker):
    fail_result = ApiTestResult(
        ok=False,
        stage="list_models",
        http_status=400,
        error_code="API_KEY_INVALID",
        message="API key not valid.",
    )
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=fail_result)
    generate_spy = mocker.patch("gcheck.api_diagnostic.gemini.generate")

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("bad-key")
        await _push_and_wait(app, pilot, screen)

        generate_spy.assert_not_called()
        error_box = screen.query_one("#api-test-error-box")
        assert error_box.text == "API key not valid."

        title, steps = api_recommendations.recommend(fail_result)
        result_text = str(screen.query_one("#api-test-result-text").renderable)
        assert title in result_text
        assert steps[0] in result_text


async def test_no_generate_capable_model_shows_fallback_message(mocker):
    list_result = ApiTestResult(
        ok=True, stage="list_models", data={"models": [_flash_model(methods=["embedContent"])]}
    )
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=list_result)
    generate_spy = mocker.patch("gcheck.api_diagnostic.gemini.generate")

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("some-key")
        await _push_and_wait(app, pilot, screen)

        generate_spy.assert_not_called()
        summary = str(screen.query_one("#api-test-summary").renderable)
        assert t("api_test_no_generate_model") in summary


async def test_generate_blocked_shows_block_reason_and_tip(mocker):
    list_result = ApiTestResult(ok=True, stage="list_models", data={"models": [_flash_model()]})
    blocked_result = ApiTestResult(
        ok=True, stage="generate", data={"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
    )
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=list_result)
    mocker.patch("gcheck.api_diagnostic.gemini.generate", return_value=blocked_result)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("some-key")
        await _push_and_wait(app, pilot, screen)

        summary = str(screen.query_one("#api-test-summary").renderable)
        assert t("api_test_blocked_reason", reason="SAFETY") in summary
        assert api_recommendations.block_reason_tip("SAFETY") in summary


async def test_recheck_button_reruns_the_test(mocker):
    # Recheck/retry only stay visible on the failure path (see
    # _on_result_inner -- both are hidden unconditionally on success).
    fail_result = ApiTestResult(ok=False, stage="list_models", error_status="TIMEOUT", message="timed out")
    list_spy = mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=fail_result)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("some-key")
        await _push_and_wait(app, pilot, screen)
        assert list_spy.call_count == 1

        # .press() rather than pilot.click(): the error box can push the
        # button row below the default 80x24 test viewport, which would
        # make a coordinate-based click raise OutOfBounds.
        screen.query_one("#btn-test-recheck", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert list_spy.call_count == 2


async def test_retry_button_pops_back_to_previous_screen(mocker):
    fail_result = ApiTestResult(ok=False, stage="list_models", error_code="API_KEY_INVALID")
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=fail_result)
    mocker.patch("gcheck.ui.screens.api_finding.find_api_keys", return_value=[])

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        await _push_and_wait(app, pilot, ApiFindingScreen())

        screen = ApiKeyTestScreen("bad-key")
        await _push_and_wait(app, pilot, screen)

        screen.query_one("#btn-test-retry", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ApiFindingScreen)


async def test_quit_button_exits_app(mocker):
    fail_result = ApiTestResult(ok=False, stage="list_models", error_code="API_KEY_INVALID")
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=fail_result)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("bad-key")
        await _push_and_wait(app, pilot, screen)

        exit_spy = mocker.patch.object(app, "exit")
        screen.query_one("#btn-test-quit", Button).press()
        await pilot.pause()
        exit_spy.assert_called_once()


async def test_troubleshooting_hint_appears_after_three_failures(mocker):
    fail_result = ApiTestResult(ok=False, stage="list_models", error_code="API_KEY_INVALID", message="bad")
    mocker.patch("gcheck.api_diagnostic.gemini.list_models", return_value=fail_result)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = ApiKeyTestScreen("bad-key")
        await _push_and_wait(app, pilot, screen)
        assert app.api_test_fail_count == 1

        hint = t("api_test_troubleshooting_hint", url=TROUBLESHOOTING_URL)
        assert hint not in str(screen.query_one("#api-test-result-text").renderable)

        for _ in range(2):
            screen.query_one("#btn-test-recheck", Button).press()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

        assert app.api_test_fail_count == 3
        assert hint in str(screen.query_one("#api-test-result-text").renderable)
