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

from gcheck.api_diagnostic.models import ApiTestResult, FoundKey


def test_found_key_to_dict():
    key = FoundKey(value="AIzaXXXX", file="app.py", line=10, var_name="GEMINI_API_KEY")
    assert key.to_dict() == {
        "value": "AIzaXXXX",
        "file": "app.py",
        "line": 10,
        "var_name": "GEMINI_API_KEY",
    }


def test_found_key_default_var_name_is_none():
    key = FoundKey(value="AIzaXXXX", file="app.py", line=10)
    assert key.to_dict()["var_name"] is None


def test_api_test_result_to_dict_defaults():
    result = ApiTestResult(ok=True, stage="list_models")
    assert result.to_dict() == {
        "ok": True,
        "stage": "list_models",
        "http_status": None,
        "error_status": None,
        "error_code": None,
        "message": "",
        "data": {},
    }


def test_api_test_result_to_dict_with_all_fields():
    result = ApiTestResult(
        ok=False,
        stage="generate",
        http_status=429,
        error_status="RESOURCE_EXHAUSTED",
        error_code="RATE_LIMIT_EXCEEDED",
        message="too many requests",
        data={"error": {"code": 429}},
    )
    d = result.to_dict()
    assert d["http_status"] == 429
    assert d["error_status"] == "RESOURCE_EXHAUSTED"
    assert d["data"] == {"error": {"code": 429}}
