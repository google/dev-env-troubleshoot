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

from gcheck.recommendations import build_diagnosis
from gcheck.api_diagnostic.recommendations import AVAILABLE_REGIONS_URL
from gcheck.i18n import set_language, t
from gcheck.network_check.models import CheckResult


def ok(name):
    return CheckResult(name=name, ok=True)


def fail(name, detail=""):
    return CheckResult(name=name, ok=False, detail=detail)


def setup_function(_):
    set_language("en")


def test_all_ok_has_no_region_hint():
    result = build_diagnosis(
        network_info={}, gateway=ok("gateway"), baseline=[ok("b1")], google=[ok("g1")]
    )
    assert AVAILABLE_REGIONS_URL not in " ".join(result["recommendations"])


def test_baseline_healthy_but_google_down_appends_region_hint():
    result = build_diagnosis(
        network_info={}, gateway=ok("gateway"), baseline=[ok("b1")], google=[fail("g1", "boom")]
    )
    expected_hint = t("diag_google_region_hint", url=AVAILABLE_REGIONS_URL)
    assert result["recommendations"][-1] == expected_hint


def test_empty_google_list_does_not_crash():
    # Guards the `primary_ok = bool(google) and google[0].ok` IndexError guard:
    # google=[] must not raise, regardless of what it recommends.
    # Note: diagnose() treats 0-of-0 google checks as "all ok", but
    # `primary_ok` (bool(google) and ...) is separately False for an empty
    # list, so build_diagnosis still appends the region hint here -- an
    # existing quirk of the current logic, not something this test asserts
    # should change.
    result = build_diagnosis(network_info={}, gateway=ok("gateway"), baseline=[ok("b1")], google=[])
    assert isinstance(result["recommendations"], list)


def test_baseline_down_never_gets_region_hint():
    result = build_diagnosis(
        network_info={}, gateway=ok("gateway"), baseline=[fail("b1")], google=[fail("g1")]
    )
    assert AVAILABLE_REGIONS_URL not in " ".join(result["recommendations"])
