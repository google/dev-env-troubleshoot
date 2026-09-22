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

from gcheck.code_setup import find_api_keys


def test_find_api_keys_delegates_to_scan_directory(monkeypatch, tmp_path):
    calls = []

    def fake_scan_directory(root):
        calls.append(root)
        return ["fake-key"]

    monkeypatch.setattr("gcheck.code_setup.scan_directory", fake_scan_directory)
    result = find_api_keys(str(tmp_path))
    assert calls == [str(tmp_path)]
    assert result == ["fake-key"]
