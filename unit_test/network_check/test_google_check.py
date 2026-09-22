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

from gcheck.network_check import google_check
from gcheck.network_check.data import GOOGLE_TARGET_DOMAIN, GOOGLE_TEST_DOMAINS


def test_google_domains_puts_target_domain_first_and_dedupes():
    assert google_check.GOOGLE_DOMAINS[0] == GOOGLE_TARGET_DOMAIN
    assert google_check.GOOGLE_DOMAINS.count(GOOGLE_TARGET_DOMAIN) == 1
    assert set(google_check.GOOGLE_DOMAINS) == {GOOGLE_TARGET_DOMAIN, *GOOGLE_TEST_DOMAINS}


def test_check_google_reachability_delegates_to_check_sites_with_google_domains(monkeypatch):
    seen = {}

    def fake_check_sites(domains):
        seen["domains"] = domains
        return ["placeholder"]

    monkeypatch.setattr(google_check, "check_sites", fake_check_sites)
    result = google_check.check_google_reachability()
    assert seen["domains"] == google_check.GOOGLE_DOMAINS
    assert result == ["placeholder"]
