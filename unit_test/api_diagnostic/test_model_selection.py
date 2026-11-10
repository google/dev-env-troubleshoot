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

import pytest

from gcheck.api_diagnostic import model_selection as ms
from gcheck.api_diagnostic.models import ApiTestResult


def listed(*names, methods=("generateContent",)):
    return ApiTestResult(
        ok=True,
        stage="list_models",
        data={"models": [{"name": f"models/{n}", "supportedGenerationMethods": list(methods)} for n in names]},
    )


def fail(http, status=None, message="", data=None):
    return ApiTestResult(
        ok=False, stage="generate", http_status=http, error_status=status, message=message, data=data or {}
    )


OK = ApiTestResult(ok=True, stage="generate", data={"candidates": []})


# ---------------------------------------------------------------------------
# user_override
# ---------------------------------------------------------------------------


def test_override_unset_is_none():
    assert ms.user_override() is None


@pytest.mark.parametrize("value", ["", "   "])
def test_override_blank_is_none(monkeypatch, value):
    monkeypatch.setenv(ms.ENV_VAR, value)
    assert ms.user_override() is None


def test_override_strips_whitespace_and_models_prefix(monkeypatch):
    monkeypatch.setenv(ms.ENV_VAR, "  models/gemini-2.5-pro ")
    assert ms.user_override() == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# DEFAULT_MODEL
# ---------------------------------------------------------------------------


def test_default_model_is_pinned_to_tested_release_model():
    # gcheck is tested on this model; changing it should be a deliberate,
    # reviewed bump.
    assert ms.DEFAULT_MODEL == "gemini-3.8-flash"


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------


def test_override_is_the_only_candidate_even_if_not_listed(monkeypatch):
    monkeypatch.setenv(ms.ENV_VAR, "my-custom-model")
    assert ms.rank_candidates(listed("gemini-flash-latest")) == ["my-custom-model"]


def test_latest_alias_beats_versioned_models():
    r = listed("gemini-2.5-pro", "gemini-9.0-flash", "gemini-flash-latest")
    assert ms.rank_candidates(r)[0] == "gemini-flash-latest"


def test_alias_order_flash_then_lite_then_pro():
    r = listed("gemini-pro-latest", "gemini-flash-lite-latest", "gemini-flash-latest")
    assert ms.rank_candidates(r)[:3] == ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest"]


def test_default_model_ranks_first_before_aliases():
    r = listed("gemini-9.0-flash", "gemini-flash-latest", "gemini-3.8-flash", "gemini-pro-latest")
    assert ms.rank_candidates(r) == ["gemini-3.8-flash", "gemini-flash-latest", "gemini-pro-latest", "gemini-9.0-flash"]


def test_default_model_not_listed_is_not_added():
    assert ms.rank_candidates(listed("gemini-2.5-flash")) == ["gemini-2.5-flash"]


def test_new_future_version_wins_automatically():
    r = listed("gemini-2.5-flash", "gemini-4.0-flash", "gemini-3.0-flash")
    assert ms.rank_candidates(r) == ["gemini-4.0-flash", "gemini-3.0-flash", "gemini-2.5-flash"]


def test_stable_before_preview_even_if_preview_is_newer():
    r = listed("gemini-9.0-flash-preview-01-2030", "gemini-2.5-flash")
    assert ms.rank_candidates(r) == ["gemini-2.5-flash", "gemini-9.0-flash-preview-01-2030"]


def test_flash_before_lite_before_pro_within_stable():
    r = listed("gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-2.5-flash")
    assert ms.rank_candidates(r) == ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]


def test_bare_name_before_pinned_suffix():
    r = listed("gemini-2.0-flash-001", "gemini-2.0-flash")
    assert ms.rank_candidates(r) == ["gemini-2.0-flash", "gemini-2.0-flash-001"]


def test_unrecognised_names_last_in_listed_order():
    r = listed("zeta-model", "gemma-3-27b-it", "gemini-2.5-flash")
    assert ms.rank_candidates(r) == ["gemini-2.5-flash", "zeta-model", "gemma-3-27b-it"]


@pytest.mark.parametrize(
    "name",
    [
        "gemini-2.5-flash-image",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-flash-native-audio-preview",
        "gemini-live-2.5-flash",
        "imagen-4.0-generate-001",
        "gemini-embedding-001",
        "aqa",
        "gemini-robotics-er-1.5-preview",
        "gemini-2.5-computer-use-preview",
    ],
)
def test_special_purpose_models_are_never_auto_picked(name):
    assert ms.rank_candidates(listed(name, "gemini-2.5-flash")) == ["gemini-2.5-flash"]


def test_retired_model_absent_from_list_is_never_picked():
    # gemini-1.5-flash was the old hardcoded first choice; once Google stops
    # listing it, ranking just moves on.
    assert ms.rank_candidates(listed("gemini-2.5-flash")) == ["gemini-2.5-flash"]


def test_models_without_generate_content_are_skipped():
    assert ms.rank_candidates(listed("text-embedding-004", methods=("embedContent",))) == []


def test_empty_and_malformed_lists_give_no_candidates():
    assert ms.rank_candidates(listed()) == []
    assert ms.rank_candidates(ApiTestResult(ok=True, stage="list_models", data={})) == []
    junk = ApiTestResult(
        ok=True,
        stage="list_models",
        data={"models": ["gemini-2.5-flash", {"name": None}, {"name": "models/x", "supportedGenerationMethods": "bad"}]},
    )
    assert ms.rank_candidates(junk) == []
    assert ms.rank_candidates(ApiTestResult(ok=True, stage="list_models", data={"models": "nope"})) == []


def test_duplicate_names_are_collapsed():
    assert ms.rank_candidates(listed("gemini-2.5-flash", "gemini-2.5-flash")) == ["gemini-2.5-flash"]


# ---------------------------------------------------------------------------
# is_model_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [
        fail(404, "NOT_FOUND", "models/gemini-1.5-flash is not found for API version v1beta"),
        fail(501, "UNIMPLEMENTED"),
        fail(400, "INVALID_ARGUMENT", "Model gemini-x is not supported for generateContent."),
        fail(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for metric generate_content_free_tier_requests",
            data={
                "error": {
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [
                                {
                                    "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                    "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                    "quotaDimensions": {"model": "gemini-2.5-pro", "location": "global"},
                                }
                            ],
                        }
                    ]
                }
            },
        ),
    ],
)
def test_model_errors_allow_fallback(result):
    assert ms.is_model_error(result) is True


@pytest.mark.parametrize(
    "result",
    [
        OK,
        fail(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."),
        fail(403, "PERMISSION_DENIED", "Generative Language API has not been used in project 123"),
        fail(429, "RESOURCE_EXHAUSTED", "Resource has been exhausted (e.g. check quota)."),
        fail(429, "RESOURCE_EXHAUSTED", "Your prepayment credits are depleted."),
        fail(500, "INTERNAL"),
        fail(503, "UNAVAILABLE"),
        ApiTestResult(ok=False, stage="generate", error_status="NETWORK_ERROR"),
        ApiTestResult(ok=False, stage="generate", error_status="TIMEOUT"),
    ],
)
def test_key_billing_network_errors_do_not_fall_back(result):
    assert ms.is_model_error(result) is False


# ---------------------------------------------------------------------------
# try_candidates
# ---------------------------------------------------------------------------


def test_try_candidates_stops_at_first_success():
    calls = []

    def attempt(m):
        calls.append(m)
        return OK

    assert ms.try_candidates(["a", "b"], attempt) == ("a", OK, ["a"])
    assert calls == ["a"]


def test_try_candidates_falls_back_on_model_error():
    results = {"a": fail(404, "NOT_FOUND"), "b": OK}
    model, result, tried = ms.try_candidates(["a", "b", "c"], results.__getitem__)
    assert (model, result, tried) == ("b", OK, ["a", "b"])


def test_try_candidates_stops_on_key_error_without_trying_others():
    bad_key = fail(400, "INVALID_ARGUMENT", "API key not valid.")
    calls = []

    def attempt(m):
        calls.append(m)
        return bad_key

    assert ms.try_candidates(["a", "b"], attempt) == ("a", bad_key, ["a"])
    assert calls == ["a"]


def test_try_candidates_caps_attempts_and_returns_last_failure():
    gone = fail(404, "NOT_FOUND")
    model, result, tried = ms.try_candidates(["a", "b", "c", "d"], lambda m: gone)
    assert tried == ["a", "b", "c"]
    assert (model, result) == ("c", gone)


def test_try_candidates_empty_list():
    assert ms.try_candidates([], lambda m: OK) == (None, None, [])
