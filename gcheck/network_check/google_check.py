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

"""Google reachability check.

Runs the same DNS + HTTPS GET site check used for the general internet
baseline (see connectivity.py) against Google's domains -- a plain ok/fail
per domain, with no DNS/TCP/TLS/HTTP layer breakdown or blocking-cause
classification.
"""

from typing import List

from .connectivity import check_sites
from .data import GOOGLE_TARGET_DOMAIN, GOOGLE_TEST_DOMAINS
from .models import CheckResult

# The target API domain first (it's what gcheck actually cares about),
# followed by a general Google presence check, deduped.
GOOGLE_DOMAINS = [GOOGLE_TARGET_DOMAIN] + [d for d in GOOGLE_TEST_DOMAINS if d != GOOGLE_TARGET_DOMAIN]


def check_google_reachability() -> List[CheckResult]:
    return check_sites(GOOGLE_DOMAINS)
