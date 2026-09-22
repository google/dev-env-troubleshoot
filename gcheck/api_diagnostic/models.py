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

"""Shared data structures for the API diagnostic tool."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FoundKey:
    """A Gemini/Google API key discovered while scanning a directory."""

    value: str
    file: str
    line: int
    var_name: Optional[str] = None  # None when matched only by the AIza… pattern

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "file": self.file,
            "line": self.line,
            "var_name": self.var_name,
        }


@dataclass
class ApiTestResult:
    """Outcome of a single call to the Gemini API.

    ``stage`` is either ``"list_models"`` or ``"generate"``. On failure,
    ``error_status`` holds Google's canonical status (e.g. ``INVALID_ARGUMENT``,
    ``PERMISSION_DENIED``, ``RESOURCE_EXHAUSTED``) and ``error_code`` the more
    specific reason (e.g. ``API_KEY_INVALID``, ``SERVICE_DISABLED``). When the
    request never reached Google (DNS/connection/timeout), ``http_status`` is
    ``None`` and ``error_status`` is a synthetic value like ``NETWORK_ERROR``.
    """

    ok: bool
    stage: str
    http_status: Optional[int] = None
    error_status: Optional[str] = None
    error_code: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "stage": self.stage,
            "http_status": self.http_status,
            "error_status": self.error_status,
            "error_code": self.error_code,
            "message": self.message,
            "data": self.data,
        }
