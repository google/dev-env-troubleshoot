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

"""Pick which Gemini model to test -- without hardcoding a single name.

Model names get retired, renamed and replaced over time, so nothing here
depends on one exact name being available. The order of precedence is:

1. **User override** -- the ``GCHECK_MODEL`` environment variable. When set,
   it is the *only* candidate (fixed mode): no silent fallback, so a typo or
   a retired name is reported instead of being papered over.
2. **Discovery** -- the models the key can actually see (``list_models``),
   filtered to text models that support ``generateContent`` and ranked:

   a. :data:`DEFAULT_MODEL` (``gemini-3.8-flash``) -- the model gcheck is
      tested against.
   b. ``-latest`` aliases (``gemini-flash-latest`` …) -- Google re-points
      these at the current model, so they survive retirements.
   c. Versioned ``gemini-<version>-<family>`` models: stable before preview,
      flash before flash-lite before pro, newest version first.
   d. Anything else that supports ``generateContent``, in listed order.

At test time :func:`try_candidates` walks that list and only moves on to the
next model when the failure is about *the model* (not found, unsupported,
per-model quota) -- never on key, billing or network errors, since those are
the diagnosis the user needs to see and switching models would hide them.
"""

import os
import re
from typing import Callable, List, Optional, Sequence, Tuple

from . import error_details
from .models import ApiTestResult

#: Environment variable that pins the model to test (fixed mode).
ENV_VAR = "GCHECK_MODEL"

#: First-choice model when ``GCHECK_MODEL`` isn't set. Pinned on purpose: it
#: is the model gcheck is tested against. Bump it deliberately, after testing.
DEFAULT_MODEL = "gemini-3.8-flash"

#: Maximum number of models :func:`try_candidates` will try before giving up.
MAX_ATTEMPTS = 3

# Google-maintained aliases that always point at a current model. Flash first:
# cheapest, and the most likely to have free-tier quota.
_ALIASES = ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest")

# Models that list generateContent but aren't general text-chat models: they
# need special input/output (audio, images, video), are embeddings, or are
# narrow task models. Never auto-picked (an explicit GCHECK_MODEL still wins).
_EXCLUDE = re.compile(
    r"(embedding|image|imagen|tts|audio|live|veo|lyria|aqa|robotics|computer-use|learnlm|banana)"
)

# gemini-<version>-<family><suffix>, e.g. gemini-2.5-flash,
# gemini-3.8-flash-preview-09-2026, gemini-2.0-flash-lite-001.
_VERSIONED = re.compile(r"^gemini-(\d+(?:\.\d+)?)-(flash-lite|flash|pro)(.*)$")
_FAMILY_ORDER = {"flash": 0, "flash-lite": 1, "pro": 2}
_PREVIEW = re.compile(r"(preview|exp)")


def user_override() -> Optional[str]:
    """The model pinned via ``GCHECK_MODEL``, or ``None`` when unset/blank."""
    value = (os.environ.get(ENV_VAR) or "").strip()
    if value.startswith("models/"):
        value = value.split("/", 1)[1]
    return value or None


def generate_capable_models(list_result: ApiTestResult) -> List[str]:
    """Bare names of listed models that support ``generateContent``, in order.

    Tolerates a non-standard schema (e.g. a proxy returning ``models`` as a
    list of strings): anything that isn't Google's object shape is skipped
    rather than raising up into the caller.
    """
    data = list_result.data if isinstance(list_result.data, dict) else {}
    models = data.get("models") or []
    if not isinstance(models, list):
        return []
    names: List[str] = []
    for m in models:
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        if not isinstance(name, str):
            continue
        bare = name.split("/", 1)[-1] if name.startswith("models/") else name
        methods = m.get("supportedGenerationMethods") or []
        if not isinstance(methods, (list, tuple)):
            continue
        if bare and "generateContent" in methods and bare not in names:
            names.append(bare)
    return names


def _score(name: str, index: int) -> Tuple:
    """Sort key: lower is better. ``index`` keeps listed order as tie-breaker."""
    if name == DEFAULT_MODEL:
        return (0, 0, 0.0, 0, index)
    if name in _ALIASES:
        return (1, _ALIASES.index(name), 0.0, 0, index)
    m = _VERSIONED.match(name)
    if m:
        version, family, suffix = float(m.group(1)), m.group(2), m.group(3)
        tier = 3 if _PREVIEW.search(suffix) else 2
        # Shorter suffix first: "gemini-2.5-flash" before "gemini-2.5-flash-001".
        return (tier, _FAMILY_ORDER[family], -version, len(suffix), index)
    return (4, 0, 0.0, 0, index)


def rank_candidates(list_result: ApiTestResult) -> List[str]:
    """Ordered list of models to try, best first. See the module docstring.

    Returns ``[GCHECK_MODEL]`` alone when the override is set, regardless of
    what ``list_models`` returned.
    """
    override = user_override()
    if override:
        return [override]

    usable = [n for n in generate_capable_models(list_result) if not _EXCLUDE.search(n)]
    indexed = sorted(enumerate(usable), key=lambda pair: _score(pair[1], pair[0]))
    return [name for _, name in indexed]


def is_model_error(result: ApiTestResult) -> bool:
    """Is this failure about the *model* (so another model might work)?

    True for: model not found / retired (404), operation not supported for
    this model (501), "model not found/supported" 400s, and 429s whose
    QuotaFailure is scoped to a specific model (e.g. a free-tier key with no
    quota for a pro model). False for everything else -- invalid/leaked key,
    permission or billing problems, network/TLS errors, server errors --
    because those would fail the same way on any model.
    """
    if result.ok:
        return False
    http = result.http_status
    status = result.error_status or ""
    message = (result.message or "").lower()

    if http == 404 or status == "NOT_FOUND":
        return True
    if http == 501 or status == "UNIMPLEMENTED":
        return True
    if (http == 400 or status == "INVALID_ARGUMENT") and "model" in message and (
        "not found" in message or "not supported" in message or "unsupported" in message
    ):
        return True
    if http == 429 or status == "RESOURCE_EXHAUSTED":
        # Billing/credits problems surface as 429 too -- not model-specific.
        if any(kw in message for kw in ("prepay", "credit", "depleted", "billing", "balance", "payment")):
            return False
        det = error_details.details_from_result_data(result.data)
        return bool(det.quota and det.quota.model)
    return False


def try_candidates(
    candidates: Sequence[str],
    attempt: Callable[[str], ApiTestResult],
    max_attempts: int = MAX_ATTEMPTS,
) -> Tuple[Optional[str], Optional[ApiTestResult], List[str]]:
    """Call ``attempt(model)`` down the candidate list until one is usable.

    Stops at the first success, or at the first failure that is *not* a
    model error (that failure is the diagnosis). Returns
    ``(model, result, tried)`` where ``model``/``result`` belong to the last
    attempt made and ``tried`` lists every model attempted, in order.
    ``model`` and ``result`` are ``None`` when ``candidates`` is empty.
    """
    tried: List[str] = []
    model: Optional[str] = None
    result: Optional[ApiTestResult] = None
    for model in list(candidates)[: max(1, max_attempts)]:
        tried.append(model)
        result = attempt(model)
        if result.ok or not is_model_error(result):
            break
    return model, result, tried
