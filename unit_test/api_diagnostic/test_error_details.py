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

from gcheck.api_diagnostic.error_details import (
    ErrorDetails,
    parse_error_details,
    details_from_result_data,
)


def test_empty_or_non_list_input_returns_empty_details():
    assert parse_error_details(None) == ErrorDetails()
    assert parse_error_details({}) == ErrorDetails()
    assert parse_error_details([]) == ErrorDetails()


def test_ignores_non_dict_entries():
    result = parse_error_details(["not a dict", 123, None])
    assert result == ErrorDetails()


def test_quota_failure_new_schema_free_tier_per_day():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "quotaMetric": "generativelanguage.googleapis.com/free_tier_requests",
                    "quotaId": "GenerateContentPerDayPerProjectPerModel-FreeTier",
                    "quotaDimensions": {"model": "gemini-1.5-flash", "location": "global"},
                    "quotaValue": "50",
                }
            ],
        }
    ]
    result = parse_error_details(details)
    assert len(result.violations) == 1
    v = result.quota
    assert v.model == "gemini-1.5-flash"
    assert v.location == "global"
    assert v.value == "50"
    assert v.is_free_tier is True
    assert v.is_per_day is True
    assert v.is_per_minute is False


def test_quota_failure_old_schema_subject_description_per_minute():
    # _classify() strips only "-"/"_" before substring-matching, so the
    # "per minute" signal has to appear without spaces (as it does in real
    # camelCase/underscored quota subject strings) to be detected.
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "subject": "RequestsPerMinutePerProjectPerModel",
                    "description": "Requests per minute exceeded",
                }
            ],
        }
    ]
    result = parse_error_details(details)
    v = result.quota
    assert v.metric == "RequestsPerMinutePerProjectPerModel"
    assert v.is_per_minute is True
    assert v.is_per_day is False
    assert v.is_free_tier is False


def test_quota_failure_skips_non_dict_violations():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": ["not-a-dict", {"quotaMetric": "m"}],
        }
    ]
    result = parse_error_details(details)
    assert len(result.violations) == 1
    assert result.violations[0].metric == "m"


def test_quota_failure_non_dict_quota_dimensions_is_ignored():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaMetric": "m", "quotaDimensions": "not-a-dict"}],
        }
    ]
    v = parse_error_details(details).quota
    assert v.model is None
    assert v.location is None


def test_retry_info_parses_seconds():
    details = [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "27s"}
    ]
    assert parse_error_details(details).retry_delay_seconds == 27.0


def test_retry_info_parses_fractional_seconds():
    details = [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "1.5s"}
    ]
    assert parse_error_details(details).retry_delay_seconds == 1.5


def test_retry_info_malformed_value_returns_none():
    details = [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "soon"}
    ]
    assert parse_error_details(details).retry_delay_seconds is None


def test_error_info_extracts_project_activation_and_service():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "reason": "SERVICE_DISABLED",
            "metadata": {
                "consumer": "projects/1234567890",
                "activationUrl": "https://example.com/activate",
                "service": "generativelanguage.googleapis.com",
            },
        }
    ]
    result = parse_error_details(details)
    assert result.reason == "SERVICE_DISABLED"
    assert result.project_number == "1234567890"
    assert result.activation_url == "https://example.com/activate"
    assert result.service == "generativelanguage.googleapis.com"


def test_error_info_consumer_not_projects_prefix_is_ignored():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "metadata": {"consumer": "folders/999"},
        }
    ]
    assert parse_error_details(details).project_number is None


def test_error_info_non_dict_metadata_is_tolerated():
    details = [
        {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "X", "metadata": "oops"}
    ]
    result = parse_error_details(details)
    assert result.reason == "X"
    assert result.project_number is None


def test_error_info_service_title_fallback():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "metadata": {"serviceTitle": "Generative Language API"},
        }
    ]
    assert parse_error_details(details).service == "Generative Language API"


def test_help_links_collected_with_default_description():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.Help",
            "links": [
                {"url": "https://a.example"},
                {"description": "Billing docs", "url": "https://b.example"},
                {"description": "no url here"},
                "not-a-dict",
            ],
        }
    ]
    result = parse_error_details(details)
    assert result.help_links == [
        ("Documentation", "https://a.example"),
        ("Billing docs", "https://b.example"),
    ]


def test_unknown_detail_type_is_ignored():
    details = [{"@type": "type.googleapis.com/google.rpc.Unknown", "foo": "bar"}]
    assert parse_error_details(details) == ErrorDetails()


def test_type_suffix_lowercased_regardless_of_case():
    details = [
        {"@type": "type.googleapis.com/google.rpc.RETRYINFO", "retryDelay": "5s"}
    ]
    assert parse_error_details(details).retry_delay_seconds == 5.0


def test_details_from_result_data_happy_path():
    data = {"error": {"details": [{"@type": ".../google.rpc.RetryInfo", "retryDelay": "3s"}]}}
    result = details_from_result_data(data)
    assert result.retry_delay_seconds == 3.0


def test_details_from_result_data_missing_or_malformed_error():
    assert details_from_result_data({}) == ErrorDetails()
    assert details_from_result_data({"error": "not-a-dict"}) == ErrorDetails()
    assert details_from_result_data(None) == ErrorDetails()
