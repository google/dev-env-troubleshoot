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

import socket
import ssl
import urllib.error

import pytest

from gcheck.network_check import utils


def make_result(ok, error_kind=None, **extra):
    d = {"ok": ok, "error_kind": error_kind}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# _layered_retry
# ---------------------------------------------------------------------------


def test_layered_retry_returns_immediately_on_success():
    attempt = lambda ctx: make_result(True)
    assert utils._layered_retry(attempt) == {"ok": True, "error_kind": None}


def test_layered_retry_timeout_then_tls12_succeeds_tags_tls13_stall():
    calls = [make_result(False, "timeout"), make_result(True)]
    attempt = lambda ctx: calls.pop(0)
    result = utils._layered_retry(attempt)
    assert result["ok"] is True
    assert result["note_tags"] == ["tls13_stall"]


def test_layered_retry_timeout_at_both_versions_keeps_original_timeout_result():
    calls = [make_result(False, "timeout", error="t1"), make_result(False, "timeout", error="t2")]
    attempt = lambda ctx: calls.pop(0)
    result = utils._layered_retry(attempt)
    assert result["error_kind"] == "timeout"
    assert result["error"] == "t1"


def test_layered_retry_timeout_then_cert_verify_then_fallback_cafile_succeeds(monkeypatch):
    monkeypatch.setattr(utils, "_find_fallback_cafile", lambda: "/fake/ca-bundle.pem")
    # build_ssl_context() would otherwise try to actually load the fake CA
    # bundle path via the real ssl module and raise FileNotFoundError.
    monkeypatch.setattr(utils, "build_ssl_context", lambda cafile=None, cap_tls12=False: "fake-ctx")
    calls = [
        make_result(False, "timeout"),
        make_result(False, "cert_verify", error="bad cert"),
        make_result(True),
    ]
    attempt = lambda ctx: calls.pop(0)
    result = utils._layered_retry(attempt)
    assert result["ok"] is True
    assert result["note_tags"] == ["tls13_stall", "local_trust_store"]


def test_layered_retry_cert_verify_no_fallback_available(monkeypatch):
    monkeypatch.setattr(utils, "_find_fallback_cafile", lambda: None)
    attempt = lambda ctx: make_result(False, "cert_verify", error="bad cert")
    result = utils._layered_retry(attempt)
    assert result["ok"] is False
    assert "no fallback found" in result["error"]


def test_layered_retry_cert_verify_fallback_found_but_still_fails(monkeypatch):
    monkeypatch.setattr(utils, "_find_fallback_cafile", lambda: "/fake/ca-bundle.pem")
    monkeypatch.setattr(utils, "build_ssl_context", lambda cafile=None, cap_tls12=False: "fake-ctx")
    calls = [
        make_result(False, "cert_verify", error="bad cert"),
        make_result(False, "cert_verify", error="still bad"),
    ]
    attempt = lambda ctx: calls.pop(0)
    result = utils._layered_retry(attempt)
    assert result["ok"] is False
    assert "known-good CA bundle" in result["error"]


def test_layered_retry_other_error_kind_returned_as_is():
    attempt = lambda ctx: make_result(False, "other", error="weird")
    result = utils._layered_retry(attempt)
    assert result == {"ok": False, "error_kind": "other", "error": "weird"}


# ---------------------------------------------------------------------------
# tcp_connect
# ---------------------------------------------------------------------------


def test_tcp_connect_success(mocker):
    fake_sock = mocker.MagicMock()
    mocker.patch("gcheck.network_check.utils.socket.create_connection", return_value=fake_sock)
    result = utils.tcp_connect("example.com", 443, timeout=1.0)
    assert result["ok"] is True
    assert result["error"] is None
    fake_sock.close.assert_called_once()


@pytest.mark.parametrize(
    "exc, expected_error",
    [
        (socket.timeout(), "timeout"),
        (ConnectionResetError(), "connection_reset"),
        (ConnectionRefusedError(), "connection_refused"),
    ],
)
def test_tcp_connect_known_failure_kinds(mocker, exc, expected_error):
    mocker.patch("gcheck.network_check.utils.socket.create_connection", side_effect=exc)
    result = utils.tcp_connect("example.com", 443, timeout=1.0)
    assert result["ok"] is False
    assert result["error"] == expected_error


def test_tcp_connect_generic_os_error_returns_str(mocker):
    mocker.patch(
        "gcheck.network_check.utils.socket.create_connection",
        side_effect=OSError("network is unreachable"),
    )
    result = utils.tcp_connect("example.com", 443, timeout=1.0)
    assert result["ok"] is False
    assert "network is unreachable" in result["error"]


# ---------------------------------------------------------------------------
# http_get / _http_get_once (via urllib.request.urlopen)
# ---------------------------------------------------------------------------


def _cm(resp):
    """Make a MagicMock usable as the object returned by urlopen()'s `with`."""
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_http_get_success(mocker):
    resp = mocker.MagicMock()
    resp.status = 200
    resp.read.return_value = b"hello world"
    _cm(resp)
    mocker.patch("gcheck.network_check.utils.urllib.request.urlopen", return_value=resp)

    result = utils.http_get("https://example.com/")
    assert result["ok"] is True
    assert result["status"] == 200
    assert result["body_preview"] == "hello world"


def test_http_get_treats_http_error_as_reachable(mocker):
    err = urllib.error.HTTPError("https://example.com/", 404, "Not Found", {}, None)
    mocker.patch("gcheck.network_check.utils.urllib.request.urlopen", side_effect=err)

    result = utils.http_get("https://example.com/")
    assert result["ok"] is True
    assert result["status"] == 404


def test_http_get_timeout_is_reported_as_timeout_kind(mocker):
    mocker.patch(
        "gcheck.network_check.utils.urllib.request.urlopen", side_effect=socket.timeout()
    )
    result = utils.http_get("https://example.com/")
    assert result["ok"] is False
    assert result["error_kind"] == "timeout"


def test_http_get_cert_verify_error_is_reported_as_cert_verify_kind(mocker):
    cert_exc = ssl.SSLCertVerificationError("certificate verify failed")
    url_err = urllib.error.URLError(cert_exc)
    mocker.patch("gcheck.network_check.utils.urllib.request.urlopen", side_effect=url_err)

    result = utils.http_get("https://example.com/")
    assert result["ok"] is False
    assert result["error_kind"] == "cert_verify"


def test_http_get_connection_refused_is_other_kind(mocker):
    url_err = urllib.error.URLError(ConnectionRefusedError("refused"))
    mocker.patch("gcheck.network_check.utils.urllib.request.urlopen", side_effect=url_err)

    result = utils.http_get("https://example.com/")
    assert result["ok"] is False
    assert result["error_kind"] == "other"


def test_http_get_sends_user_agent_and_extra_headers(mocker):
    resp = mocker.MagicMock()
    resp.status = 200
    resp.read.return_value = b""
    _cm(resp)
    urlopen = mocker.patch(
        "gcheck.network_check.utils.urllib.request.urlopen", return_value=resp
    )

    utils.http_get("https://example.com/", headers={"X-Test": "1"})
    request = urlopen.call_args.args[0]
    # Request.add_header() stores keys via str.capitalize() (e.g. "X-test"),
    # and get_header() looks up the exact string given -- so the caller must
    # pass the same capitalized form back, not the original header name.
    assert request.get_header("X-Test".capitalize()) == "1"
    assert request.get_header("User-Agent".capitalize()) == utils.USER_AGENT


# ---------------------------------------------------------------------------
# resolve_system
# ---------------------------------------------------------------------------


def test_resolve_system_success_dedupes_and_sorts_ips(monkeypatch):
    def fake_getaddrinfo(hostname, port, family):
        return [
            (family, None, None, "", ("2.2.2.2", 0)),
            (family, None, None, "", ("1.1.1.1", 0)),
            (family, None, None, "", ("1.1.1.1", 0)),
        ]

    monkeypatch.setattr(utils.socket, "getaddrinfo", fake_getaddrinfo)
    result = utils.resolve_system("example.com", timeout=2.0)
    assert result["ok"] is True
    assert result["ips"] == ["1.1.1.1", "2.2.2.2"]


def test_resolve_system_dns_failure(monkeypatch):
    def fake_getaddrinfo(hostname, port, family):
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(utils.socket, "getaddrinfo", fake_getaddrinfo)
    result = utils.resolve_system("nonexistent.invalid", timeout=2.0)
    assert result["ok"] is False
    assert result["ips"] == []
    assert "not known" in result["error"]


def test_resolve_system_times_out(monkeypatch):
    import time

    def slow_getaddrinfo(hostname, port, family):
        time.sleep(0.4)
        return []

    monkeypatch.setattr(utils.socket, "getaddrinfo", slow_getaddrinfo)
    result = utils.resolve_system("example.com", timeout=0.05)
    assert result["ok"] is False
    assert "timed out" in result["error"]
