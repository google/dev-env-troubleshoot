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

"""Combine the connectivity diagnosis with gcheck's regional-availability
hint into one displayable result.

`diagnosis_i18n.diagnose()` decides *whether* Google is reachable; when
it's specifically Google that's unreachable (not the general internet),
this adds a pointer to Gemini's supported-regions list. Both the
diagnosis/recommendation text and this module's own strings are translated
via gcheck's i18n system so the whole narrative renders in the user's
selected language; only the raw low-level probe output (from the vendored
`network_check` package) stays English.
"""

from typing import List

from .api_diagnostic.recommendations import AVAILABLE_REGIONS_URL
from .diagnosis_i18n import diagnose
from .i18n import t
from .network_check.models import CheckResult


def build_diagnosis(
    network_info: dict,
    gateway: CheckResult,
    baseline: List[CheckResult],
    google: List[CheckResult],
) -> dict:
    result = diagnose(network_info, gateway, baseline, google)
    diagnosis = result["diagnosis"]
    recommendations = list(result["recommendations"])

    # google[0] is always the target API domain (see network_check.data.GOOGLE_TEST_DOMAINS)
    # -- `diagnosis`/`recommendations` above already reflect all of `google` via diagnose().
    # Guard the index anyway: an empty list here would turn a diagnosis render
    # into an IndexError on the UI thread.
    primary_ok = bool(google) and google[0].ok

    # Matches the same baseline_ok gate diagnosis_i18n.diagnose() uses to decide
    # whether the problem is local/ISP-level (handled there, with an early return)
    # versus Google-specific (handled here, below).
    baseline_healthy = any(c.ok for c in baseline)

    if baseline_healthy and not primary_ok:
        recommendations.append(t("diag_google_region_hint", url=AVAILABLE_REGIONS_URL))

    return {
        "diagnosis": diagnosis,
        "recommendations": recommendations,
    }
