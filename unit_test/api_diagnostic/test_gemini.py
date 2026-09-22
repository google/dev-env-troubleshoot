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

from gcheck.api_diagnostic.gemini import (
    block_reason,
    model_names,
    pick_generate_model,
    reply_text,
)
from gcheck.api_diagnostic.models import ApiTestResult


def list_result(models):
    return ApiTestResult(ok=True, stage="list_models", data={"models": models})


def gen_result(data):
    return ApiTestResult(ok=True, stage="generate", data=data)


def test_model_names_strips_models_prefix():
    r = list_result([{"name": "models/gemini-1.5-flash"}, {"name": "bare-name"}])
    assert model_names(r) == ["gemini-1.5-flash", "bare-name"]


def test_model_names_skips_non_dict_entries_and_missing_names():
    r = list_result(["not-a-dict", {"no_name_key": True}, {"name": 123}, {"name": ""}])
    assert model_names(r) == []


def test_model_names_empty_when_no_models_key():
    assert model_names(ApiTestResult(ok=True, stage="list_models", data={})) == []


def test_pick_generate_model_prefers_known_flash_model():
    r = list_result(
        [
            {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},
        ]
    )
    assert pick_generate_model(r) == "gemini-1.5-flash"


def test_pick_generate_model_falls_back_to_any_supporting_model():
    r = list_result(
        [{"name": "models/some-model", "supportedGenerationMethods": ["generateContent"]}]
    )
    assert pick_generate_model(r) == "some-model"


def test_pick_generate_model_ignores_models_without_generate_content():
    r = list_result([{"name": "models/embedding-model", "supportedGenerationMethods": ["embedContent"]}])
    assert pick_generate_model(r) is None


def test_pick_generate_model_no_models_returns_none():
    assert pick_generate_model(list_result([])) is None


def test_pick_generate_model_tolerates_malformed_entries():
    r = list_result(["not-a-dict", {"name": 123, "supportedGenerationMethods": "not-a-list"}])
    assert pick_generate_model(r) is None


def test_reply_text_extracts_first_candidate_text():
    r = gen_result({"candidates": [{"content": {"parts": [{"text": "Hi"}, {"text": " there"}]}}]})
    assert reply_text(r) == "Hi there"


def test_reply_text_skips_candidate_with_null_content():
    r = gen_result({"candidates": [{"content": None}, {"content": {"parts": [{"text": "ok"}]}}]})
    assert reply_text(r) == "ok"


def test_reply_text_no_candidates_returns_empty_string():
    assert reply_text(gen_result({})) == ""
    assert reply_text(gen_result({"candidates": "not-a-list"})) == ""


def test_reply_text_whitespace_only_is_treated_as_empty():
    r = gen_result({"candidates": [{"content": {"parts": [{"text": "   "}]}}]})
    assert reply_text(r) == ""


def test_block_reason_from_prompt_feedback():
    r = gen_result({"promptFeedback": {"blockReason": "SAFETY"}})
    assert block_reason(r) == "SAFETY"


def test_block_reason_from_finish_reason():
    r = gen_result({"candidates": [{"finishReason": "RECITATION"}]})
    assert block_reason(r) == "RECITATION"


def test_block_reason_normal_finish_reasons_are_not_blocks():
    for reason in ("STOP", "MAX_TOKENS"):
        r = gen_result({"candidates": [{"finishReason": reason}]})
        assert block_reason(r) is None


def test_block_reason_none_when_nothing_present():
    assert block_reason(gen_result({})) is None
