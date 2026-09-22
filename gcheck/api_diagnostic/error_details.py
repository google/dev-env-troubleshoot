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

"""Parse Google's structured ``error.details[]`` into something we can diagnose.

Google API errors carry a list of well-known RPC detail types under
``error.details``. The ones that matter here:

* ``google.rpc.QuotaFailure`` -- which quota was exhausted (metric, id, model,
  limit value). The metric/id strings reveal the *tier* (they contain
  ``free_tier``) and the *scope* (``PerMinute`` vs ``PerDay``).
* ``google.rpc.RetryInfo``   -- how long to wait (``retryDelay: "27s"``).
* ``google.rpc.ErrorInfo``   -- ``reason`` plus ``metadata`` with the project
  number (``consumer``), an ``activationUrl`` (for a disabled service), and the
  ``service`` name.
* ``google.rpc.Help``        -- documentation links.

Everything here is best-effort and tolerant of missing/renamed fields, since the
exact shape has shifted over time and isn't a documented contract.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class QuotaViolation:
    metric: Optional[str] = None
    quota_id: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    value: Optional[str] = None
    is_free_tier: bool = False
    is_per_day: bool = False
    is_per_minute: bool = False


@dataclass
class ErrorDetails:
    reason: Optional[str] = None
    retry_delay_seconds: Optional[float] = None
    violations: List[QuotaViolation] = field(default_factory=list)
    project_number: Optional[str] = None
    activation_url: Optional[str] = None
    service: Optional[str] = None
    help_links: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def quota(self) -> Optional[QuotaViolation]:
        """The first quota violation, if any (the usual single-violation case)."""
        return self.violations[0] if self.violations else None


def _type_suffix(detail: Dict[str, Any]) -> str:
    """Return the trailing type name from an ``@type`` URL, lowercased."""
    return str(detail.get("@type", "")).rsplit("/", 1)[-1].split(".")[-1].lower()


def _parse_duration(value: Any) -> Optional[float]:
    """Parse a protobuf duration string like ``"27s"`` / ``"1.5s"`` into seconds."""
    if value is None:
        return None
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)s?\s*$", str(value))
    return float(m.group(1)) if m else None


def _classify(*texts: Optional[str]) -> Tuple[bool, bool, bool]:
    """Return ``(is_free_tier, is_per_day, is_per_minute)`` from quota id/metric text."""
    blob = " ".join(t for t in texts if t).lower().replace("-", "").replace("_", "")
    is_free = "freetier" in blob
    is_day = "perday" in blob or "daily" in blob
    is_min = "perminute" in blob or "permin" in blob
    return is_free, is_day, is_min


def _parse_quota_failure(detail: Dict[str, Any]) -> List[QuotaViolation]:
    out: List[QuotaViolation] = []
    for v in detail.get("violations", []) or []:
        if not isinstance(v, dict):
            continue
        dims = v.get("quotaDimensions", {}) or {}
        if not isinstance(dims, dict):
            dims = {}
        # Newer responses use quotaMetric/quotaId; older ones only subject/description.
        metric = v.get("quotaMetric") or v.get("subject")
        quota_id = v.get("quotaId")
        # Classify over every string field so both formats work.
        is_free, is_day, is_min = _classify(
            metric, quota_id, v.get("description"), json.dumps(dims)
        )
        out.append(
            QuotaViolation(
                metric=metric,
                quota_id=quota_id,
                model=dims.get("model"),
                location=dims.get("location"),
                value=str(v.get("quotaValue")) if v.get("quotaValue") is not None else None,
                is_free_tier=is_free,
                is_per_day=is_day,
                is_per_minute=is_min,
            )
        )
    return out


def parse_error_details(details: Any) -> ErrorDetails:
    """Parse an ``error.details`` list into an :class:`ErrorDetails`."""
    result = ErrorDetails()
    if not isinstance(details, list):
        return result

    for detail in details:
        if not isinstance(detail, dict):
            continue
        kind = _type_suffix(detail)

        if kind == "quotafailure":
            result.violations.extend(_parse_quota_failure(detail))

        elif kind == "retryinfo":
            result.retry_delay_seconds = _parse_duration(detail.get("retryDelay"))

        elif kind == "errorinfo":
            result.reason = detail.get("reason") or result.reason
            meta = detail.get("metadata", {}) or {}
            if not isinstance(meta, dict):
                meta = {}
            consumer = meta.get("consumer", "")  # e.g. "projects/1234567890"
            if isinstance(consumer, str) and consumer.startswith("projects/"):
                result.project_number = consumer.split("/", 1)[1]
            result.activation_url = meta.get("activationUrl") or result.activation_url
            result.service = meta.get("service") or meta.get("serviceTitle") or result.service

        elif kind == "help":
            for link in detail.get("links", []) or []:
                if isinstance(link, dict) and link.get("url"):
                    result.help_links.append((link.get("description", "Documentation"), link["url"]))

    return result


def details_from_result_data(data: Dict[str, Any]) -> ErrorDetails:
    """Convenience: pull ``error.details`` out of an ApiTestResult.data dict."""
    error = (data or {}).get("error", {})
    if not isinstance(error, dict):
        return ErrorDetails()
    return parse_error_details(error.get("details", []))
