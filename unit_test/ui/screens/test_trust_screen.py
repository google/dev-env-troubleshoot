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
from gcheck.i18n import t
from gcheck.network_check.models import CheckResult
from gcheck.ui.screens.diagnostic import DiagnosticScreen


def _stub_out_diagnostic_network_calls(mocker):
    """DiagnosticScreen.on_mount immediately kicks off real network checks
    in background worker threads (gate check, gateway/baseline/Google
    reachability). Stub every one of them so pushing that screen in a test
    never touches the network."""
    mocker.patch("gcheck.ui.screens.diagnostic.check_gate", return_value=True)
    mocker.patch(
        "gcheck.ui.screens.diagnostic.check_network_info",
        return_value={
            "platform": "Linux",
            "interface": None,
            "connection_type": "unknown",
            "local_ip": None,
            "gateway": None,
            "dns_servers": [],
            "is_tunnel": False,
        },
    )
    mocker.patch(
        "gcheck.ui.screens.diagnostic.check_gateway",
        return_value=CheckResult(name="gateway", ok=True),
    )
    mocker.patch("gcheck.ui.screens.diagnostic.check_general_baseline", return_value=[])
    mocker.patch("gcheck.ui.screens.diagnostic.check_google_reachability", return_value=[])


async def test_allow_pushes_diagnostic_screen(mocker):
    _stub_out_diagnostic_network_calls(mocker)

    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#btn-allow")
        await pilot.pause()
        assert isinstance(app.screen, DiagnosticScreen)


async def test_deny_exits_app_with_trust_denied_message(mocker):
    app = GcheckApp(flag_lang="en")
    async with app.run_test() as pilot:
        await pilot.pause()
        # Patch the instance's exit() rather than letting it run for real --
        # the real GcheckApp.exit() arms a watchdog thread that force-kills
        # the process after a grace period if shutdown doesn't complete in
        # time, which has no business running inside a test.
        exit_spy = mocker.patch.object(app, "exit")
        await pilot.click("#btn-deny")
        await pilot.pause()
        exit_spy.assert_called_once()
        assert exit_spy.call_args.kwargs.get("message") == t("trust_denied")
