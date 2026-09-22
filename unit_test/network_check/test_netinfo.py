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

from gcheck.network_check import netinfo

SAMPLE_IPCONFIG_ETHERNET = """
Windows IP Configuration

Ethernet adapter Ethernet:

   Connection-specific DNS Suffix  . :
   IPv4 Address. . . . . . . . . . . : 192.168.1.42
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 192.168.1.1
"""

SAMPLE_IPCONFIG_WIFI_WITH_DNS = """
Wireless LAN adapter Wi-Fi:

   Connection-specific DNS Suffix  . :
   IPv4 Address. . . . . . . . . . . : 10.0.0.15
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 10.0.0.1
   DNS Servers . . . . . . . . . . . : 8.8.8.8
                                       1.1.1.1
"""

SAMPLE_IPCONFIG_TAILSCALE = """
Ethernet adapter Ethernet:

   IPv4 Address. . . . . . . . . . . : 192.168.1.42
   Default Gateway . . . . . . . . . : 192.168.1.1

Ethernet adapter Tailscale:

   Connection-specific DNS Suffix  . :
   IPv4 Address. . . . . . . . . . . : 100.101.102.103
   Subnet Mask . . . . . . . . . . . : 255.255.255.255
   Default Gateway . . . . . . . . . :
"""

SAMPLE_IPCONFIG_TAILSCALE_DISCONNECTED = """
Ethernet adapter Ethernet:

   IPv4 Address. . . . . . . . . . . : 192.168.1.42
   Default Gateway . . . . . . . . . : 192.168.1.1

Ethernet adapter Tailscale:

   Autoconfiguration IPv4 Address. . : 169.254.10.20
   Subnet Mask . . . . . . . . . . . : 255.255.0.0
   Default Gateway . . . . . . . . . :
"""

SAMPLE_MACOS_ROUTE_GET_DEFAULT = """   route to: default
destination: default
       mask: default
    gateway: 192.168.1.1
  interface: en0
"""

SAMPLE_LINUX_IP_ROUTE = "default via 192.168.1.1 dev wlan0 proto dhcp metric 600 \n"

SAMPLE_MACOS_HARDWARE_PORTS = """Hardware Port: Wi-Fi
Device: en0
Ethernet Address: aa:bb:cc:dd:ee:ff

Hardware Port: Ethernet
Device: en1
Ethernet Address: 11:22:33:44:55:66

"""


def test_windows_default_iface_prefers_gateway_adapter():
    assert netinfo._default_iface_windows(SAMPLE_IPCONFIG_ETHERNET) == "Ethernet"


def test_windows_gateway_extracted():
    assert netinfo._gateway_windows(SAMPLE_IPCONFIG_ETHERNET) == "192.168.1.1"


def test_windows_dns_servers_multiline():
    assert netinfo._dns_servers_windows(SAMPLE_IPCONFIG_WIFI_WITH_DNS) == ["8.8.8.8", "1.1.1.1"]


def test_windows_dns_servers_none_present():
    assert netinfo._dns_servers_windows(SAMPLE_IPCONFIG_ETHERNET) == []


def test_windows_active_tailscale_adapter_preferred_over_gateway_adapter():
    assert netinfo._default_iface_windows(SAMPLE_IPCONFIG_TAILSCALE) == "Tailscale"


def test_windows_disconnected_tailscale_adapter_is_not_preferred():
    # Only an APIPA address (no real IPv4) -- must fall back to the
    # gateway-bearing adapter instead of misreporting a dead tunnel.
    assert netinfo._default_iface_windows(SAMPLE_IPCONFIG_TAILSCALE_DISCONNECTED) == "Ethernet"


def test_windows_iface_type_classification():
    assert netinfo._iface_type_windows("Ethernet") == "Ethernet"
    assert netinfo._iface_type_windows("Wi-Fi") == "Wi-Fi"
    assert netinfo._iface_type_windows("Tailscale") == "VPN/Tunnel"
    assert netinfo._iface_type_windows(None) == "unknown"
    assert netinfo._iface_type_windows("Bluetooth Network Connection") == "unknown"


def test_windows_is_tunnel_iface_matches_known_vpn_clients():
    for name in ("Tailscale", "WireGuard Tunnel", "TAP-Windows Adapter V9", "VPN - Client"):
        assert netinfo._is_tunnel_iface_windows(name) is True
    assert netinfo._is_tunnel_iface_windows("Ethernet") is False
    assert netinfo._is_tunnel_iface_windows(None) is False


def test_macos_iface_type_wifi(monkeypatch):
    monkeypatch.setattr(
        netinfo, "run_cmd", lambda cmd: (0, SAMPLE_MACOS_HARDWARE_PORTS, "")
    )
    assert netinfo._iface_type_macos("en0") == "Wi-Fi"
    assert netinfo._iface_type_macos("en1") == "Ethernet"
    assert netinfo._iface_type_macos("en9") == "unknown"


def test_macos_iface_type_tunnel_short_circuits_without_run_cmd(monkeypatch):
    def boom(cmd):
        raise AssertionError("run_cmd should not be called for a tunnel iface")

    monkeypatch.setattr(netinfo, "run_cmd", boom)
    assert netinfo._iface_type_macos("utun4") == "VPN/Tunnel"


def test_is_tunnel_iface_generic():
    for name in ("utun3", "tun0", "tap0", "ppp0", "wg0", "tailscale0", "ipsec0"):
        assert netinfo._is_tunnel_iface(name) is True
    assert netinfo._is_tunnel_iface("en0") is False
    assert netinfo._is_tunnel_iface(None) is False


def test_linux_default_iface_and_gateway(monkeypatch):
    monkeypatch.setattr(netinfo, "run_cmd", lambda cmd: (0, SAMPLE_LINUX_IP_ROUTE, ""))
    assert netinfo._default_iface_linux() == "wlan0"
    assert netinfo._gateway_linux() == "192.168.1.1"


def test_linux_default_iface_command_failure_returns_none(monkeypatch):
    monkeypatch.setattr(netinfo, "run_cmd", lambda cmd: (1, "", "no route"))
    assert netinfo._default_iface_linux() is None
    assert netinfo._gateway_linux() is None


def test_linux_iface_type_by_name_prefix():
    assert netinfo._iface_type_linux("wlan0") == "Wi-Fi"
    assert netinfo._iface_type_linux("eth0") == "Ethernet"
    assert netinfo._iface_type_linux(None) == "unknown"


def test_macos_default_iface_from_route_output(monkeypatch):
    monkeypatch.setattr(netinfo, "run_cmd", lambda cmd: (0, SAMPLE_MACOS_ROUTE_GET_DEFAULT, ""))
    assert netinfo._default_iface_macos() == "en0"
    assert netinfo._gateway_macos() == "192.168.1.1"


def test_dns_servers_resolv_conf(tmp_path, monkeypatch):
    resolv = tmp_path / "resolv.conf"
    resolv.write_text("nameserver 8.8.8.8\nnameserver 1.1.1.1\n")

    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/etc/resolv.conf":
            return real_open(resolv, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    assert netinfo._dns_servers_resolv_conf() == ["8.8.8.8", "1.1.1.1"]


def test_dns_servers_resolv_conf_missing_file_returns_empty(monkeypatch):
    def fake_open(path, *args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr("builtins.open", fake_open)
    assert netinfo._dns_servers_resolv_conf() == []


def test_get_local_ip_returns_sockname(mocker):
    fake_sock = mocker.MagicMock()
    fake_sock.__enter__.return_value = fake_sock
    fake_sock.__exit__.return_value = False
    fake_sock.getsockname.return_value = ("192.168.1.5", 54321)
    mocker.patch("gcheck.network_check.netinfo.socket.socket", return_value=fake_sock)
    assert netinfo.get_local_ip() == "192.168.1.5"


def test_get_local_ip_returns_none_on_os_error(mocker):
    mocker.patch("gcheck.network_check.netinfo.socket.socket", side_effect=OSError())
    assert netinfo.get_local_ip() is None


def test_get_network_summary_dispatches_by_platform(monkeypatch):
    monkeypatch.setattr(netinfo, "SYSTEM", "Windows")
    monkeypatch.setattr(netinfo, "_windows_ipconfig_all", lambda: SAMPLE_IPCONFIG_ETHERNET)
    monkeypatch.setattr(netinfo, "get_local_ip", lambda: "192.168.1.42")

    summary = netinfo.get_network_summary()
    assert summary["platform"] == "Windows"
    assert summary["interface"] == "Ethernet"
    assert summary["connection_type"] == "Ethernet"
    assert summary["gateway"] == "192.168.1.1"
    assert summary["local_ip"] == "192.168.1.42"
    assert summary["is_tunnel"] is False


def test_get_network_summary_unknown_platform_returns_safe_defaults(monkeypatch):
    monkeypatch.setattr(netinfo, "SYSTEM", "Plan9")
    monkeypatch.setattr(netinfo, "get_local_ip", lambda: None)

    summary = netinfo.get_network_summary()
    assert summary["interface"] is None
    assert summary["connection_type"] == "unknown"
    assert summary["gateway"] is None
    assert summary["dns_servers"] == []
    assert summary["is_tunnel"] is False
