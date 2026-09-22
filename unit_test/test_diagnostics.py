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

import gcheck.diagnostics as diagnostics
from gcheck.i18n import set_language, t
from gcheck.network_check.models import CheckResult


def setup_function(_):
    set_language("en")


def test_collect_notices_dedupes_tags_across_baseline_and_google():
    baseline = [CheckResult(name="a", ok=True, data={"note_tags": ["tls13_stall"]})]
    google = [
        CheckResult(name="b", ok=True, data={"note_tags": ["tls13_stall", "local_trust_store"]}),
        CheckResult(name="c", ok=True, data={}),
    ]
    notices = diagnostics.collect_notices(baseline, google)
    assert notices == [
        t("diag_tls13_stall_hint"),
        t("diag_local_trust_store_hint"),
    ]


def test_collect_notices_empty_when_no_tags_present():
    baseline = [CheckResult(name="a", ok=True)]
    google = [CheckResult(name="b", ok=True)]
    assert diagnostics.collect_notices(baseline, google) == []


def test_check_network_info_delegates_to_netinfo(monkeypatch):
    monkeypatch.setattr(diagnostics.netinfo, "get_network_summary", lambda: {"platform": "Linux"})
    assert diagnostics.check_network_info() == {"platform": "Linux"}


def test_check_gateway_delegates_to_connectivity(monkeypatch):
    sentinel = CheckResult(name="gateway", ok=True)
    monkeypatch.setattr(
        diagnostics.connectivity, "check_gateway", lambda gw, is_tunnel=False: sentinel
    )
    assert diagnostics.check_gateway("192.168.1.1") is sentinel


def test_run_diagnostics_wires_everything_together(monkeypatch):
    gateway_result = CheckResult(name="gateway", ok=True)
    baseline_results = [CheckResult(name="b1", ok=True)]
    google_results = [CheckResult(name="g1", ok=True)]

    monkeypatch.setattr(
        diagnostics,
        "check_network_info",
        lambda: {"gateway": "192.168.1.1", "is_tunnel": False},
    )
    monkeypatch.setattr(diagnostics, "check_gateway", lambda gw, is_tunnel=False: gateway_result)
    monkeypatch.setattr(diagnostics, "check_general_baseline", lambda: baseline_results)
    monkeypatch.setattr(diagnostics, "check_google_reachability", lambda: google_results)

    result = diagnostics.run_diagnostics()

    assert result["network_info"] == {"gateway": "192.168.1.1", "is_tunnel": False}
    assert result["gateway"] is gateway_result
    assert result["baseline"] == baseline_results
    assert result["google"] == google_results
    assert result["notices"] == []
