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

from .api_diagnostic.models import FoundKey
from .api_diagnostic.scanner import scan_directory


def find_api_keys(cwd: str) -> list[FoundKey]:
    """Scan `cwd` for existing Gemini/Google API keys."""
    return scan_directory(cwd)
