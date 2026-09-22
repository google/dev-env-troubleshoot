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

import os
import tempfile
from pathlib import Path

from gcheck.api_diagnostic.scanner import _scan_line, scan_directory

STANDARD_KEY = "AIza" + "a" * 35
AUTH_KEY = "AQ." + "b" * 25


def test_named_assignment_with_standard_key():
    hits = _scan_line(f"GEMINI_API_KEY={STANDARD_KEY}")
    assert hits == [(STANDARD_KEY, "GEMINI_API_KEY")]


def test_named_assignment_with_export_and_quotes():
    hits = _scan_line(f'export GOOGLE_API_KEY="{STANDARD_KEY}"')
    assert hits == [(STANDARD_KEY, "GOOGLE_API_KEY")]


def test_named_assignment_placeholder_value_is_skipped():
    hits = _scan_line("GEMINI_API_KEY=your_api_key_here")
    assert hits == []


def test_named_assignment_placeholder_variants():
    for placeholder in ["changeme", "<GEMINI_API_KEY>", "{{API_KEY}}", "xxxxxxxx", "***", "...", "dummy", "TODO"]:
        assert _scan_line(f"GOOGLE_GENAI_API_KEY={placeholder}") == [], placeholder


def test_value_pattern_without_matching_var_name():
    line = f"const cfg = {{ token: '{STANDARD_KEY}' }};"
    hits = _scan_line(line)
    assert hits == [(STANDARD_KEY, None)]


def test_value_pattern_recovers_generic_var_name():
    line = f"API_KEY={STANDARD_KEY}"
    hits = _scan_line(line)
    assert hits == [(STANDARD_KEY, "API_KEY")]


def test_auth_key_shape_is_detected():
    hits = _scan_line(f"GEMINI_API_KEY={AUTH_KEY}")
    assert hits == [(AUTH_KEY, "GEMINI_API_KEY")]


def test_named_hit_not_duplicated_by_value_pattern():
    # A key matched via KEY_VAR_RE shouldn't also show up as a second,
    # var_name=None hit from GOOGLE_KEY_RE.
    hits = _scan_line(f"GEMINI_API_KEY={STANDARD_KEY}")
    assert len(hits) == 1


def test_line_with_no_key_returns_no_hits():
    assert _scan_line("just some regular code, nothing to see here") == []


def test_scan_directory_finds_key_and_dedupes(tmp_path):
    (tmp_path / "app.py").write_text(f'GEMINI_API_KEY = "{STANDARD_KEY}"\nOTHER = "{STANDARD_KEY}"\n')
    found = scan_directory(str(tmp_path))
    assert len(found) == 1
    assert found[0].value == STANDARD_KEY
    assert found[0].var_name == "GEMINI_API_KEY"
    assert found[0].file == "app.py"
    assert found[0].line == 1


def test_scan_directory_skips_denylisted_dirs(tmp_path):
    skipped = tmp_path / "node_modules"
    skipped.mkdir()
    (skipped / "leaked.js").write_text(f"key = '{STANDARD_KEY}'")
    found = scan_directory(str(tmp_path))
    assert found == []


def test_scan_directory_skips_oversized_file(tmp_path, monkeypatch):
    big = tmp_path / "big.env"
    big.write_text(f"GEMINI_API_KEY={STANDARD_KEY}\n")
    monkeypatch.setattr(
        "gcheck.api_diagnostic.scanner.MAX_FILE_SIZE", 1
    )
    found = scan_directory(str(tmp_path))
    assert found == []


def test_scan_directory_ignores_placeholder_only_env_example(tmp_path):
    (tmp_path / ".env.example").write_text("GEMINI_API_KEY=your_api_key_here\n")
    assert scan_directory(str(tmp_path)) == []


def test_scan_directory_skips_symlink_escaping_root(tmp_path):
    # The symlink target deliberately lives outside pytest's own tmp_path
    # tree (in an independently-managed tempfile.TemporaryDirectory instead
    # of tmp_path.parent, which is pytest's shared numbered-dir area) so a
    # leftover/dangling symlink here can't confuse pytest's own tmpdir
    # retention cleanup on Windows.
    root = tmp_path / "project"
    root.mkdir()
    link = root / "escape.txt"

    with tempfile.TemporaryDirectory() as outside_dir:
        outside = Path(outside_dir) / "outside_secret.txt"
        outside.write_text(f"GEMINI_API_KEY={STANDARD_KEY}\n")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            import pytest

            pytest.skip("symlinks not supported/permitted in this environment")

        try:
            found = scan_directory(str(root))
            assert found == []
        finally:
            link.unlink()
