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

"""Localized diagnosis narrative.

Composes the diagnosis/recommendation sentences through gcheck's i18n
system (`t()`) instead of hardcoded English, so the result renders in the
user's selected language.
"""

from typing import Dict, List

from .i18n import t
from .network_check.models import CheckResult


def diagnose(
    network_info: Dict,
    gateway: CheckResult,
    baseline: List[CheckResult],
    google: List[CheckResult],
) -> Dict:
    lines: List[str] = []
    recs: List[str] = []

    baseline_ok = any(c.ok for c in baseline)
    google_ok_count = sum(1 for c in google if c.ok)
    google_total = len(google)

    if not gateway.ok and not baseline_ok:
        lines.append(t("diag_gateway_down"))
        recs.append(t("diag_gateway_down_rec"))
        return {"diagnosis": " ".join(lines), "recommendations": recs}

    if not gateway.ok and baseline_ok:
        # The gateway probe is just a TCP:80 connect -- many routers don't run a web
        # server on that port at all, and on a VPN/tunnel the gateway may not carry
        # general traffic either way. The baseline sites succeeding already proves the
        # local network/ISP path works, so don't let this timeout override that.
        lines.append(t("diag_gateway_down_but_baseline_ok"))

    if not baseline_ok:
        # Can't tell "local network/ISP is down" apart from "this network is
        # broadly filtering outbound traffic" here -- there's no separate
        # control site to distinguish the two, so the message below has to
        # cover both possibilities.
        lines.append(t("diag_baseline_down"))
        recs.append(t("diag_baseline_down_rec1"))
        return {"diagnosis": " ".join(lines), "recommendations": recs}

    if google_ok_count == google_total:
        lines.append(t("diag_all_ok"))
        recs.append(t("diag_all_ok_rec"))
        return {"diagnosis": " ".join(lines), "recommendations": recs}

    lines.append(
        t(
            "diag_google_targeted",
            baseline_ok=sum(1 for c in baseline if c.ok),
            baseline_total=len(baseline),
            google_failed=google_total - google_ok_count,
            google_total=google_total,
        )
    )
    for c in google:
        if not c.ok:
            lines.append(t("diag_google_domain_failed", domain=c.name, detail=c.detail))
    recs.append(t("diag_recheck_periodically"))

    return {"diagnosis": " ".join(lines), "recommendations": recs}
