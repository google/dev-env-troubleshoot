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

from gcheck.network_check import connectivity


def test_check_gateway_no_gateway_and_no_tunnel_is_not_ok():
    result = connectivity.check_gateway("", is_tunnel=False)
    assert result.ok is False
    assert result.name == "gateway"


def test_check_gateway_no_gateway_but_is_tunnel_is_ok():
    result = connectivity.check_gateway("", is_tunnel=True)
    assert result.ok is True
    assert "VPN/tunnel" in result.detail


def test_check_gateway_refused_connection_still_counts_as_reachable(monkeypatch):
    monkeypatch.setattr(
        connectivity, "tcp_connect", lambda host, port, timeout=3.0: {"error": "connection_refused", "latency_ms": 1.2}
    )
    result = connectivity.check_gateway("192.168.1.1")
    assert result.ok is True
    assert "reachable" in result.detail


def test_check_gateway_timeout_is_unreachable(monkeypatch):
    monkeypatch.setattr(
        connectivity, "tcp_connect", lambda host, port, timeout=3.0: {"error": "timeout", "latency_ms": 3000.0}
    )
    result = connectivity.check_gateway("192.168.1.1")
    assert result.ok is False
    assert "unreachable" in result.detail


def test_check_site_dns_failure_short_circuits_before_http(monkeypatch):
    monkeypatch.setattr(connectivity, "resolve_system", lambda domain, timeout=5.0: {"ok": False, "error": "nxdomain"})

    def boom(*a, **kw):
        raise AssertionError("http_get should not be called when DNS fails")

    monkeypatch.setattr(connectivity, "http_get", boom)
    result = connectivity._check_site("example.com")
    assert result.ok is False
    assert "DNS failed" in result.detail


def test_check_site_success_carries_ips_and_note_tags(monkeypatch):
    monkeypatch.setattr(
        connectivity, "resolve_system", lambda domain, timeout=5.0: {"ok": True, "ips": ["1.2.3.4"]}
    )
    monkeypatch.setattr(
        connectivity,
        "http_get",
        lambda url, timeout=8.0: {"ok": True, "status": 200, "latency_ms": 12.3, "note_tags": ["tls13_stall"]},
    )
    result = connectivity._check_site("example.com")
    assert result.ok is True
    assert result.data["ips"] == ["1.2.3.4"]
    assert result.data["note_tags"] == ["tls13_stall"]


def test_check_site_dns_ok_but_http_fails(monkeypatch):
    monkeypatch.setattr(
        connectivity, "resolve_system", lambda domain, timeout=5.0: {"ok": True, "ips": ["1.2.3.4"]}
    )
    monkeypatch.setattr(
        connectivity, "http_get", lambda url, timeout=8.0: {"ok": False, "error": "connection_refused", "latency_ms": 5.0}
    )
    result = connectivity._check_site("example.com")
    assert result.ok is False
    assert "HTTPS failed" in result.detail
    assert result.data["ips"] == ["1.2.3.4"]


def test_check_sites_empty_list_returns_empty_without_crashing():
    assert connectivity.check_sites([]) == []


def test_check_sites_runs_each_domain(monkeypatch):
    monkeypatch.setattr(
        connectivity, "_check_site", lambda domain: connectivity.CheckResult(name=domain, ok=True)
    )
    results = connectivity.check_sites(["a.com", "b.com"])
    assert {r.name for r in results} == {"a.com", "b.com"}
    assert all(r.ok for r in results)


def test_check_general_baseline_uses_configured_domains(monkeypatch):
    seen = {}

    def fake_check_sites(domains):
        seen["domains"] = domains
        return ["placeholder"]

    monkeypatch.setattr(connectivity, "check_sites", fake_check_sites)
    result = connectivity.check_general_baseline()
    assert seen["domains"] == connectivity.GENERAL_BASELINE_DOMAINS
    assert result == ["placeholder"]
