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

from gcheck.network_check.models import CheckResult


def test_check_result_defaults():
    r = CheckResult(name="site", ok=True)
    assert r.detail == ""
    assert r.latency_ms is None
    assert r.data == {}


def test_check_result_to_dict():
    r = CheckResult(name="site", ok=False, detail="DNS failed", latency_ms=123.4, data={"ips": ["1.2.3.4"]})
    assert r.to_dict() == {
        "name": "site",
        "ok": False,
        "detail": "DNS failed",
        "latency_ms": 123.4,
        "data": {"ips": ["1.2.3.4"]},
    }


def test_check_result_data_default_is_not_shared_between_instances():
    a = CheckResult(name="a", ok=True)
    b = CheckResult(name="b", ok=True)
    a.data["x"] = 1
    assert b.data == {}
