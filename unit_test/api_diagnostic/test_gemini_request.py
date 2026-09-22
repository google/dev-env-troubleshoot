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

import io
import json
import socket
import ssl
import sys
import urllib.error

import pytest

from gcheck.api_diagnostic import gemini


@pytest.fixture(autouse=True)
def _reset_fallback_cafile_cache():
    """gemini._fallback_cafile_cache is a process-global memo; don't leak
    one test's monkeypatched result into the next."""
    gemini._fallback_cafile_cache.clear()
    yield
    gemini._fallback_cafile_cache.clear()


def _cm(resp):
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _http_error(code, payload=None, raw_body=None):
    if raw_body is None:
        raw_body = json.dumps(payload if payload is not None else {}).encode("utf-8")
    return urllib.error.HTTPError("https://example.com", code, "reason", {}, io.BytesIO(raw_body))


# ---------------------------------------------------------------------------
# _find_fallback_cafile
# ---------------------------------------------------------------------------


def test_find_fallback_cafile_uses_certifi_when_available(monkeypatch):
    import types

    fake_certifi = types.SimpleNamespace(where=lambda: "/fake/certifi-bundle.pem")
    monkeypatch.setitem(sys.modules, "certifi", fake_certifi)

    assert gemini._find_fallback_cafile() == "/fake/certifi-bundle.pem"


def test_find_fallback_cafile_falls_back_to_candidate_when_certifi_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "certifi", None)  # forces ImportError
    monkeypatch.setattr(
        gemini.os.path, "isfile", lambda path: path == "/etc/ssl/certs/ca-certificates.crt"
    )
    assert gemini._find_fallback_cafile() == "/etc/ssl/certs/ca-certificates.crt"


def test_find_fallback_cafile_none_when_nothing_found(monkeypatch):
    monkeypatch.setitem(sys.modules, "certifi", None)
    monkeypatch.setattr(gemini.os.path, "isfile", lambda path: False)
    assert gemini._find_fallback_cafile() is None


def test_find_fallback_cafile_result_is_cached(monkeypatch):
    calls = []

    import types

    def where():
        calls.append(1)
        return "/fake/certifi-bundle.pem"

    monkeypatch.setitem(sys.modules, "certifi", types.SimpleNamespace(where=where))
    assert gemini._find_fallback_cafile() == "/fake/certifi-bundle.pem"
    assert gemini._find_fallback_cafile() == "/fake/certifi-bundle.pem"
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# _is_cert_verify_error
# ---------------------------------------------------------------------------


def test_is_cert_verify_error_direct_instance():
    assert gemini._is_cert_verify_error(ssl.SSLCertVerificationError("bad cert")) is True


def test_is_cert_verify_error_wrapped_in_urlerror():
    exc = urllib.error.URLError(ssl.SSLCertVerificationError("bad cert"))
    assert gemini._is_cert_verify_error(exc) is True


def test_is_cert_verify_error_matches_message_text():
    exc = OSError("[SSL: CERTIFICATE_VERIFY_FAILED] self signed certificate")
    assert gemini._is_cert_verify_error(exc) is True


def test_is_cert_verify_error_false_for_unrelated_error():
    assert gemini._is_cert_verify_error(ConnectionRefusedError("refused")) is False


# ---------------------------------------------------------------------------
# _ssl_contexts
# ---------------------------------------------------------------------------


def test_ssl_contexts_single_when_no_fallback(monkeypatch):
    monkeypatch.setattr(gemini, "_find_fallback_cafile", lambda: None)
    assert len(gemini._ssl_contexts()) == 1


def test_ssl_contexts_includes_fallback_when_found(monkeypatch):
    monkeypatch.setattr(gemini, "_find_fallback_cafile", lambda: "/fake/ca-bundle.pem")
    monkeypatch.setattr(gemini.ssl, "create_default_context", lambda cafile=None: f"ctx({cafile})")
    contexts = gemini._ssl_contexts()
    assert contexts == ["ctx(None)", "ctx(/fake/ca-bundle.pem)"]


# ---------------------------------------------------------------------------
# _request
# ---------------------------------------------------------------------------


def test_request_success_returns_parsed_payload(mocker):
    resp = mocker.MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps({"models": []}).encode("utf-8")
    _cm(resp)
    mocker.patch("gcheck.api_diagnostic.gemini.urllib.request.urlopen", return_value=resp)

    result = gemini._request("https://example.com/v1beta/models", "list_models")
    assert result.ok is True
    assert result.http_status == 200
    assert result.data == {"models": []}


def test_request_sends_api_key_as_header_not_query_param(mocker):
    resp = mocker.MagicMock()
    resp.status = 200
    resp.read.return_value = b"{}"
    _cm(resp)
    urlopen = mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen", return_value=resp
    )

    gemini._request("https://example.com/v1beta/models", "list_models", api_key="AQ.secret")
    request = urlopen.call_args.args[0]
    assert request.get_header("X-goog-api-key".capitalize()) == "AQ.secret"
    assert "AQ.secret" not in request.full_url


def test_request_post_with_body_sets_content_type_and_json_data(mocker):
    resp = mocker.MagicMock()
    resp.status = 200
    resp.read.return_value = b"{}"
    _cm(resp)
    urlopen = mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen", return_value=resp
    )

    gemini._request(
        "https://example.com/generate", "generate", method="POST", body={"contents": []}
    )
    request = urlopen.call_args.args[0]
    assert request.get_method() == "POST"
    assert request.get_header("Content-type".capitalize()) == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {"contents": []}


def test_request_http_error_parses_status_code_and_message(mocker):
    err = _http_error(
        429,
        {
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded",
                "details": [{"reason": "RATE_LIMIT_EXCEEDED"}],
            }
        },
    )
    mocker.patch("gcheck.api_diagnostic.gemini.urllib.request.urlopen", side_effect=err)

    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is False
    assert result.http_status == 429
    assert result.error_status == "RESOURCE_EXHAUSTED"
    assert result.error_code == "RATE_LIMIT_EXCEEDED"
    assert result.message == "Quota exceeded"
    assert result.data["error"]["status"] == "RESOURCE_EXHAUSTED"


def test_request_http_error_with_unparseable_body_falls_back_to_generic_message(mocker):
    err = _http_error(500, raw_body=b"not json")
    mocker.patch("gcheck.api_diagnostic.gemini.urllib.request.urlopen", side_effect=err)

    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is False
    assert result.http_status == 500
    assert result.message == "HTTP 500"
    assert result.error_status is None
    assert result.error_code is None


def test_request_http_error_details_without_reason_leaves_error_code_none(mocker):
    err = _http_error(400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"foo": "bar"}]}})
    mocker.patch("gcheck.api_diagnostic.gemini.urllib.request.urlopen", side_effect=err)

    result = gemini._request("https://example.com/generate", "generate")
    assert result.error_status == "INVALID_ARGUMENT"
    assert result.error_code is None


def test_request_timeout(mocker):
    mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen", side_effect=socket.timeout()
    )
    result = gemini._request("https://example.com/generate", "generate", timeout=5.0)
    assert result.ok is False
    assert result.error_status == "TIMEOUT"
    assert "5" in result.message


def test_request_ssl_error_non_cert_is_tls_error(mocker):
    mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen",
        side_effect=ssl.SSLError("handshake failure"),
    )
    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is False
    assert result.error_status == "TLS_ERROR"


def test_request_network_error_dns_or_connection_failure(mocker):
    url_err = urllib.error.URLError(ConnectionRefusedError("refused"))
    mocker.patch("gcheck.api_diagnostic.gemini.urllib.request.urlopen", side_effect=url_err)

    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is False
    assert result.error_status == "NETWORK_ERROR"
    assert "refused" in result.message


def test_request_unexpected_value_error_is_network_error(mocker):
    # A ValueError raised by urlopen() itself (e.g. a malformed response),
    # as opposed to one from constructing the Request beforehand -- that
    # happens outside _request()'s try/except and isn't this branch's concern.
    mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen",
        side_effect=ValueError("bad url"),
    )
    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is False
    assert result.error_status == "NETWORK_ERROR"
    assert "bad url" in result.message


def test_request_cert_verify_error_retries_with_fallback_context_and_succeeds(mocker):
    mocker.patch("gcheck.api_diagnostic.gemini._ssl_contexts", return_value=["ctx1", "ctx2"])

    resp = mocker.MagicMock()
    resp.status = 200
    resp.read.return_value = b"{}"
    _cm(resp)

    cert_err = urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
    mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen",
        side_effect=[cert_err, resp],
    )

    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is True
    assert result.http_status == 200


def test_request_cert_verify_error_at_every_context_returns_tls_cert_error(mocker):
    mocker.patch("gcheck.api_diagnostic.gemini._ssl_contexts", return_value=["ctx1", "ctx2"])
    cert_err = urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
    mocker.patch(
        "gcheck.api_diagnostic.gemini.urllib.request.urlopen",
        side_effect=[cert_err, cert_err],
    )

    result = gemini._request("https://example.com/generate", "generate")
    assert result.ok is False
    assert result.error_status == "TLS_CERT_ERROR"


# ---------------------------------------------------------------------------
# list_models / generate wrappers
# ---------------------------------------------------------------------------


def test_list_models_calls_request_with_models_endpoint(mocker):
    spy = mocker.patch(
        "gcheck.api_diagnostic.gemini._request", return_value="sentinel"
    )
    result = gemini.list_models("my-key", timeout=3.0)
    assert result == "sentinel"
    spy.assert_called_once_with(f"{gemini.BASE}/models", "list_models", api_key="my-key", timeout=3.0)


def test_generate_prefixes_bare_model_name_with_models(mocker):
    spy = mocker.patch("gcheck.api_diagnostic.gemini._request", return_value="sentinel")
    gemini.generate("my-key", "gemini-1.5-flash", timeout=7.0, prompt="hi")
    args, kwargs = spy.call_args
    assert args[0] == f"{gemini.BASE}/models/gemini-1.5-flash:generateContent"
    assert kwargs["method"] == "POST"
    assert kwargs["body"] == {"contents": [{"parts": [{"text": "hi"}]}]}
    assert kwargs["api_key"] == "my-key"
    assert kwargs["timeout"] == 7.0


def test_generate_leaves_already_prefixed_model_name_untouched(mocker):
    spy = mocker.patch("gcheck.api_diagnostic.gemini._request", return_value="sentinel")
    gemini.generate("my-key", "models/gemini-1.5-flash")
    args, _ = spy.call_args
    assert args[0] == f"{gemini.BASE}/models/gemini-1.5-flash:generateContent"
