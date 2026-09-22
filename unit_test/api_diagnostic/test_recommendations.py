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

from gcheck.api_diagnostic.models import ApiTestResult
from gcheck.api_diagnostic.recommendations import (
    block_reason_tip,
    is_billing_issue,
    recommend,
    steps_to_get_key,
)


def result(**kwargs):
    kwargs.setdefault("ok", False)
    kwargs.setdefault("stage", "generate")
    return ApiTestResult(**kwargs)


def test_leaked_key_is_detected_before_other_checks():
    r = result(http_status=400, error_status="INVALID_ARGUMENT", message="API key has been publicly exposed.")
    title, steps = recommend(r)
    assert title == "api_rec_leaked_title"
    assert len(steps) == 4


def test_invalid_key_by_error_code():
    r = result(error_code="API_KEY_INVALID")
    title, _ = recommend(r)
    assert title == "api_rec_invalid_title"


def test_invalid_key_by_http_and_status():
    r = result(http_status=400, error_status="INVALID_ARGUMENT")
    title, _ = recommend(r)
    assert title == "api_rec_invalid_title"


def test_location_restricted_free_tier_message():
    r = result(error_status="FAILED_PRECONDITION", message="The free tier is not available in your country.")
    title, _ = recommend(r)
    assert title == "api_rec_location_freetier_title"


def test_location_restricted_generic_message():
    r = result(error_status="FAILED_PRECONDITION", message="This API is not available in your location.")
    title, _ = recommend(r)
    assert title == "api_rec_location_title"


def test_failed_precondition_unrelated_to_location_falls_through_to_fallback():
    r = result(error_status="FAILED_PRECONDITION", message="Billing must be enabled for this project.")
    title, _ = recommend(r)
    assert title == "api_rec_fallback_title"


def test_bad_credential_401():
    r = result(http_status=401)
    title, _ = recommend(r)
    assert title == "api_rec_bad_cred_title"


def test_bad_credential_access_token_type_unsupported():
    r = result(error_code="ACCESS_TOKEN_TYPE_UNSUPPORTED")
    title, _ = recommend(r)
    assert title == "api_rec_bad_cred_title"


def test_permission_denied_service_disabled_uses_activation_url_and_project():
    r = result(
        http_status=403,
        error_code="SERVICE_DISABLED",
        data={
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "metadata": {
                            "consumer": "projects/42",
                            "activationUrl": "https://example.com/enable",
                        },
                    }
                ]
            }
        },
    )
    title, steps = recommend(r)
    assert title == "api_rec_permission_title"
    assert "  https://example.com/enable" in steps


def test_permission_denied_without_activation_url_falls_back_to_console_link_with_project():
    r = result(
        http_status=403,
        data={
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "metadata": {"consumer": "projects/42"},
                    }
                ]
            }
        },
    )
    _, steps = recommend(r)
    assert any("project=42" in s for s in steps)


def test_rate_limit_429_with_no_details_routes_to_generic_quota_guidance():
    r = result(http_status=429)
    title, _ = recommend(r)
    assert title == "api_rec_quota_generic_title"


def test_model_not_found_404():
    r = result(http_status=404)
    title, _ = recommend(r)
    assert title == "api_rec_model_notfound_title"


def test_unimplemented_501():
    r = result(http_status=501)
    title, _ = recommend(r)
    assert title == "api_rec_unimplemented_title"


def test_transient_server_error_by_http_code():
    for code in (408, 500, 503, 504):
        r = result(http_status=code)
        title, _ = recommend(r)
        assert title == "api_rec_transient_title", code


def test_transient_server_error_by_status_string():
    for status in ("ABORTED", "DEADLINE_EXCEEDED", "INTERNAL", "UNAVAILABLE"):
        r = result(error_status=status)
        title, _ = recommend(r)
        assert title == "api_rec_transient_title", status


def test_conflict_409_is_not_treated_as_transient():
    # ABORTED (retryable) and ALREADY_EXISTS (not) both map to HTTP 409 --
    # bare http==409 must not be matched, only the specific status string.
    r = result(http_status=409, error_status="ALREADY_EXISTS")
    title, _ = recommend(r)
    assert title == "api_rec_fallback_title"


def test_tls_cert_error():
    r = result(error_status="TLS_CERT_ERROR")
    title, _ = recommend(r)
    assert title == "api_rec_tls_cert_title"


def test_network_unreachable_statuses():
    for status in ("NETWORK_ERROR", "TIMEOUT", "TLS_ERROR"):
        r = result(error_status=status)
        title, _ = recommend(r)
        assert title == "api_rec_network_title", status


def test_unrecognized_error_falls_back():
    r = result(http_status=418, error_status="IM_A_TEAPOT")
    title, steps = recommend(r)
    assert title == "api_rec_fallback_title"
    assert len(steps) == 1


def test_quota_billing_issue_detected_from_message():
    r = result(http_status=429, message="Your prepay balance is depleted.")
    title, _ = recommend(r)
    assert title == "api_rec_billing_title"


def test_quota_billing_issue_detected_from_help_link():
    r = result(
        http_status=429,
        data={
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.Help",
                        "links": [{"description": "Billing", "url": "https://cloud.google.com/billing/x"}],
                    }
                ]
            }
        },
    )
    title, _ = recommend(r)
    assert title == "api_rec_billing_title"


def test_quota_no_structured_details_uses_generic_guidance():
    r = result(http_status=429, message="quota exceeded")
    title, _ = recommend(r)
    assert title == "api_rec_quota_generic_title"


def test_quota_free_tier_per_day_with_model_and_value():
    r = result(
        http_status=429,
        data={
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaMetric": "free_tier_requests",
                                "quotaId": "PerDay-FreeTier",
                                "quotaDimensions": {"model": "gemini-1.5-flash"},
                                "quotaValue": "50",
                            }
                        ],
                    }
                ]
            }
        },
    )
    title, steps = recommend(r)
    # combo == "daily_freetier"; recommend() capitalizes the first letter
    # of the composed phrase before appending the model/period suffixes.
    assert title.startswith("Api_rec_quota_phrase_daily_freetier")
    # No locale loaded in this test module, so t() returns the raw key
    # rather than an interpolated "Limit hit: 50" -- assert the key chosen.
    assert "api_rec_quota_limit_hit_with_id" in steps


def test_quota_paid_tier_per_minute_with_retry_delay():
    r = result(
        http_status=429,
        data={
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaMetric": "requests_per_minute"}],
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "12s",
                    },
                ]
            }
        },
    )
    title, steps = recommend(r)
    assert title.startswith("Api_rec_quota_phrase_perminute")
    assert "api_rec_quota_retry_delay" in steps


def test_is_billing_issue_true_and_false():
    billing = result(http_status=429, message="payment failed")
    not_billing = result(http_status=429, message="rate limit exceeded")
    assert is_billing_issue(billing) is True
    assert is_billing_issue(not_billing) is False


def test_block_reason_tip_maps_known_and_unknown_reasons():
    assert block_reason_tip("SAFETY") == "api_block_tip_safety"
    assert block_reason_tip("PROHIBITED_CONTENT") == "api_block_tip_safety"
    assert block_reason_tip("RECITATION") == "api_block_tip_recitation"
    assert block_reason_tip("LANGUAGE") == "api_block_tip_language"
    assert block_reason_tip("SOMETHING_ELSE") == "api_block_tip_default"
    assert block_reason_tip("") == "api_block_tip_default"


def test_steps_to_get_key_is_a_nonempty_ordered_list():
    steps = steps_to_get_key()
    assert len(steps) == 5
    assert "aistudio.google.com" in steps[0]
