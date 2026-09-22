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

"""Static reference data: test domains for the two connectivity checks.

  internet access check - general, non-Google baseline (sanity check that
                           *some* internet connectivity works at all,
                           independent of Google)
  google reachability check - the actual target: Google services
"""

GENERAL_BASELINE_DOMAINS = [
    "www.bing.com",
    "www.python.org",
    "www.cloudflare.com",
]

GOOGLE_TARGET_DOMAIN = "generativelanguage.googleapis.com"

GOOGLE_TEST_DOMAINS = [
    "google.com",
    "www.google.com",
    "googleapis.com",
    "gemini.google.com",
    "aistudio.google.com",
    "cloud.google.com",
]

REQUEST_TIMEOUT = 8.0
