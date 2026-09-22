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

from concurrent.futures import ThreadPoolExecutor

from .network_check import connectivity, google_check, netinfo
from .network_check.data import GOOGLE_TARGET_DOMAIN
from .network_check.models import CheckResult


def check_network_info() -> dict:
    return netinfo.get_network_summary()


def check_gateway(gateway: str, is_tunnel: bool = False) -> CheckResult:
    return connectivity.check_gateway(gateway, is_tunnel)


def check_general_baseline() -> list[CheckResult]:
    return connectivity.check_general_baseline()


def check_google_reachability() -> list[CheckResult]:
    return google_check.check_google_reachability()


_NOTE_KEYS = {
    "local_trust_store": "diag_local_trust_store_hint",
    "tls13_stall": "diag_tls13_stall_hint",
}


def collect_notices(baseline: list[CheckResult], google: list[CheckResult]) -> list[str]:
    from .i18n import t

    tags_seen: list[str] = []

    def _add(data: dict) -> None:
        for tag in data.get("note_tags", []):
            if tag not in tags_seen:
                tags_seen.append(tag)

    for c in baseline + google:
        _add(c.data)
    return [t(_NOTE_KEYS[tag]) for tag in tags_seen]


def run_diagnostics() -> dict:
    """Blocking, all-in-one diagnostic run for non-interactive callers
    (the online-mode agent tool). The TUI does not use this -- it fires
    each check as its own worker so results can be shown live as they
    land; see app.py DiagnosticScreen.
    """
    with ThreadPoolExecutor(max_workers=4) as executor:
        f_info = executor.submit(check_network_info)
        f_google = executor.submit(check_google_reachability)

        info = f_info.result()
        f_gateway = executor.submit(check_gateway, info.get("gateway") or "", info.get("is_tunnel", False))
        f_baseline = executor.submit(check_general_baseline)

        gateway = f_gateway.result()
        baseline = f_baseline.result()
        google = f_google.result()

    return {
        "network_info": info,
        "gateway": gateway,
        "baseline": baseline,
        "google": google,
        "notices": collect_notices(baseline, google),
    }
