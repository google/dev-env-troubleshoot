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

from gcheck.diagnosis_i18n import diagnose
from gcheck.i18n import set_language, t
from gcheck.network_check.models import CheckResult


def ok(name, **kw):
    return CheckResult(name=name, ok=True, **kw)


def fail(name, detail="", **kw):
    return CheckResult(name=name, ok=False, detail=detail, **kw)


def setup_function(_):
    set_language("en")


def test_gateway_down_and_baseline_down_short_circuits():
    result = diagnose(
        {}, gateway=fail("gateway"), baseline=[fail("b1"), fail("b2")], google=[fail("g1")]
    )
    assert result["diagnosis"] == t("diag_gateway_down")
    assert result["recommendations"] == [t("diag_gateway_down_rec")]


def test_gateway_down_but_baseline_ok_notes_it_then_continues_to_all_ok():
    result = diagnose(
        {}, gateway=fail("gateway"), baseline=[ok("b1")], google=[ok("g1")]
    )
    expected = " ".join([t("diag_gateway_down_but_baseline_ok"), t("diag_all_ok")])
    assert result["diagnosis"] == expected
    assert result["recommendations"] == [t("diag_all_ok_rec")]


def test_baseline_down_with_gateway_ok_short_circuits():
    result = diagnose(
        {}, gateway=ok("gateway"), baseline=[fail("b1"), fail("b2")], google=[fail("g1")]
    )
    assert result["diagnosis"] == t("diag_baseline_down")
    assert result["recommendations"] == [t("diag_baseline_down_rec1")]


def test_all_ok():
    result = diagnose(
        {}, gateway=ok("gateway"), baseline=[ok("b1")], google=[ok("g1"), ok("g2")]
    )
    assert result["diagnosis"] == t("diag_all_ok")
    assert result["recommendations"] == [t("diag_all_ok_rec")]


def test_google_partially_targeted():
    baseline = [ok("b1"), ok("b2")]
    google = [ok("g1"), fail("g2", detail="DNS failed: timeout")]
    result = diagnose({}, gateway=ok("gateway"), baseline=baseline, google=google)

    expected_lines = [
        t(
            "diag_google_targeted",
            baseline_ok=2,
            baseline_total=2,
            google_failed=1,
            google_total=2,
        ),
        t("diag_google_domain_failed", domain="g2", detail="DNS failed: timeout"),
    ]
    assert result["diagnosis"] == " ".join(expected_lines)
    assert result["recommendations"] == [t("diag_recheck_periodically")]


def test_google_all_failed_lists_every_failed_domain():
    google = [fail("g1", detail="d1"), fail("g2", detail="d2")]
    result = diagnose({}, gateway=ok("gateway"), baseline=[ok("b1")], google=google)
    assert t("diag_google_domain_failed", domain="g1", detail="d1") in result["diagnosis"]
    assert t("diag_google_domain_failed", domain="g2", detail="d2") in result["diagnosis"]
