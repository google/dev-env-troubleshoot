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

"""Scan a development directory for Gemini / Google API keys.

Two detection strategies run per line:

1. **Env-style assignment** -- a variable whose name looks like a Gemini/Google
   API key (``GEMINI_API_KEY``, ``GOOGLE_API_KEY``, ``GOOGLE_GENAI_API_KEY`` …)
   assigned any non-empty value, unless that value is an obvious placeholder
   (``your_api_key_here``, ``<GEMINI_API_KEY>``, ``changeme`` …) -- these are
   common in ``.env.example`` files and aren't real keys. This strategy
   catches keys even if Google ever changes the ``AIza`` prefix, and lets us
   report the variable name.
2. **Value pattern** -- any token shaped like a Google API key. This catches
   keys embedded in JSON/YAML/code where the surrounding name isn't obviously a
   key. Two shapes are recognised:
     * the legacy "Standard" key: ``AIza`` + 35 url-safe chars, and
     * the newer "Auth" key: an ``AQ.`` prefix followed by an opaque token
       (rolled out in 2026 as ``AIza`` keys are phased out).

The scan is read-only; it never writes discovered keys anywhere.
"""

import os
import re
from typing import List, Optional, Set, Tuple

from .models import FoundKey

# Google API key value shapes:
#   * Legacy "Standard" key: "AIza" + 35 url-safe base64 chars (39 total).
#   * Newer "Auth" key:      "AQ." + an opaque, dot-separated token.
# The Auth-key body length isn't a documented contract, so we match it loosely
# (a run of url-safe/base64 chars and dots) and lean on the variable-name check
# for anything this misses.
GOOGLE_KEY_RE = re.compile(
    r"(?:AIza[0-9A-Za-z\-_]{35}|AQ\.[A-Za-z0-9_.\-]{20,})"
)

# Env-style assignment whose NAME looks like a Gemini/Google API key.
# Tolerates a leading `export `, optional quotes, and surrounding whitespace.
KEY_VAR_RE = re.compile(
    r"""(?ix)                      # case-insensitive, verbose
    (?:^|\bexport\s+)              # line start or `export `
    (?P<name>[A-Z0-9_]*            # var name …
        (?:GEMINI|GENAI|GOOGLE)    # … mentioning a Google product …
        [A-Z0-9_]*API[A-Z0-9_]*KEY # … and API…KEY
    )
    \s*[:=]\s*                     # = or : assignment
    (?P<q>['"]?)                   # optional opening quote
    (?P<value>[^'"\s#]+)           # the value (no quotes/space/comment)
    (?P=q)                         # matching closing quote
    """
)

# Placeholder values commonly left in `.env.example` / README snippets next
# to a real-looking key name (e.g. `GEMINI_API_KEY=your_api_key_here`) --
# these aren't leaked keys and shouldn't be reported as findings.
PLACEHOLDER_RE = re.compile(
    r"""(?ix)
    ^(?:
        your[_-].*key.*        |   # your_api_key_here, your-key-here
        <.*>                   |   # <your-api-key>, <GEMINI_API_KEY>
        \{\{.*\}\}              |   # {{API_KEY}}
        x{4,}                  |   # xxxxxxxx
        \*{3,}                 |   # ***
        \.{3,}                 |   # ...
        change[_-]?me          |
        replace[_-]?me         |
        insert[_-].*key.*      |
        placeholder | dummy | example | fake | todo |
        test[_-]?key           |
        redacted | none | null | undefined
    )$
    """
)

# Same shape as KEY_VAR_RE but without the "mentions Gemini/Genai/Google"
# requirement -- used only as a fallback to recover the variable name for a
# value-pattern hit (e.g. `API_KEY=AQ....` or `ML_RESEARCH_API_KEY=AIza...`)
# whose name doesn't happen to mention a Google product.
GENERIC_VAR_RE = re.compile(
    r"""(?ix)
    (?:^|\bexport\s+)
    (?P<name>[A-Z0-9_]+)
    \s*[:=]\s*
    (?P<q>['"]?)
    (?P<value>[^'"\s#]+)
    (?P=q)
    """
)

# Directories we never descend into.
SKIP_DIRS = {
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "env",
    ".env.d",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".idea",
    ".vscode",
    ".next",
    ".cache",
}

# Skip files larger than this (bytes) — real keys live in small config/source files.
MAX_FILE_SIZE = 1_000_000


def _within(root_real: str, path: str) -> bool:
    """True if ``path``'s real (symlink-resolved) location is inside ``root_real``."""
    real = os.path.realpath(path)
    if real == root_real:
        return True
    try:
        return os.path.commonpath([root_real, real]) == root_real
    except ValueError:
        # Different drives on Windows -- definitely outside the scanned tree.
        return False


def _read_text(path: str) -> Optional[str]:
    """Return the file's text, or None if it's too big or not utf-8 text."""
    try:
        if os.path.getsize(path) > MAX_FILE_SIZE:
            return None
    except OSError:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (UnicodeDecodeError, OSError):
        return None


def _scan_line(line: str) -> List[Tuple[str, Optional[str]]]:
    """Return (value, var_name) pairs found on one line.

    Named assignments are reported with their variable name; any remaining
    ``AIza…`` tokens not already captured are reported with ``var_name=None``.
    """
    hits: List[Tuple[str, Optional[str]]] = []
    named_values: List[str] = []

    for m in KEY_VAR_RE.finditer(line):
        value = m.group("value").strip()
        if value and not PLACEHOLDER_RE.match(value):
            hits.append((value, m.group("name")))
            named_values.append(value)

    for m in GOOGLE_KEY_RE.finditer(line):
        value = m.group(0)
        # Skip a bare AIza… match that's already part of a named assignment
        # (a correctly-sized key is captured identically by both patterns).
        if any(value in nv for nv in named_values):
            continue
        hits.append((value, _find_var_name(line, value)))

    return hits


def _find_var_name(line: str, value: str) -> Optional[str]:
    """Recover the assignment's variable name for a value-pattern hit, e.g.
    `API_KEY=AQ....`, even though its name doesn't mention Gemini/Genai/Google."""
    for m in GENERIC_VAR_RE.finditer(line):
        if m.group("value").strip() == value:
            return m.group("name")
    return None


def scan_directory(root: str) -> List[FoundKey]:
    """Recursively scan ``root`` and return the API keys found, de-duplicated.

    Keys are de-duplicated by value (the first source location wins) and returned
    in discovery order.
    """
    found: List[FoundKey] = []
    seen: Set[str] = set()
    root_real = os.path.realpath(root)

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped/hidden-heavy directories in place so os.walk won't enter them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            path = os.path.join(dirpath, filename)
            # os.walk already won't descend symlinked *directories* (followlinks
            # defaults to False), but open() still follows a symlinked *file*.
            # Skip any whose real target sits outside the scanned tree, so a
            # symlink in the project can't pull in e.g. ~/.aws/credentials.
            if os.path.islink(path) and not _within(root_real, path):
                continue
            text = _read_text(path)
            if text is None:
                continue

            try:
                rel = os.path.relpath(path, root)
            except ValueError:
                # Windows raises when path and root sit on different drives
                # (e.g. a directory junction into another volume).
                rel = path
            for lineno, line in enumerate(text.splitlines(), start=1):
                for value, var_name in _scan_line(line):
                    if value in seen:
                        continue
                    seen.add(value)
                    found.append(FoundKey(value=value, file=rel, line=lineno, var_name=var_name))

    return found
