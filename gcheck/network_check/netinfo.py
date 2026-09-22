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

"""Detect how the machine is currently connected: interface name/type
(Wi-Fi vs Ethernet vs other), local IP, default gateway, configured DNS
servers. Best-effort and cross-platform (macOS / Linux / Windows); any
piece that can't be determined on a given platform is reported as
"unknown" rather than raising.
"""

import platform
import re
import socket
from typing import Dict, List, Optional

from .utils import run_cmd

SYSTEM = platform.system()  # "Darwin", "Linux", "Windows"


def get_local_ip() -> Optional[str]:
    """Outbound-facing local IP, found via a connect() on a UDP socket.

    This never actually sends a packet (UDP connect() just records a
    default destination), so it works offline-safely and without needing
    any platform-specific parsing.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _default_iface_macos() -> Optional[str]:
    rc, out, _ = run_cmd(["route", "-n", "get", "default"])
    if rc == 0:
        m = re.search(r"interface:\s*(\S+)", out)
        if m:
            return m.group(1)
    return None


def _default_iface_linux() -> Optional[str]:
    rc, out, _ = run_cmd(["ip", "route", "show", "default"])
    if rc == 0:
        m = re.search(r"dev\s+(\S+)", out)
        if m:
            return m.group(1)
    return None


def _gateway_macos() -> Optional[str]:
    rc, out, _ = run_cmd(["route", "-n", "get", "default"])
    if rc == 0:
        m = re.search(r"gateway:\s*(\S+)", out)
        if m:
            return m.group(1)
    return None


def _gateway_linux() -> Optional[str]:
    rc, out, _ = run_cmd(["ip", "route", "show", "default"])
    if rc == 0:
        m = re.search(r"default via\s+(\S+)", out)
        if m:
            return m.group(1)
    return None


def _is_tunnel_iface(iface: Optional[str]) -> bool:
    """True for point-to-point VPN/tunnel interfaces (Tailscale, WireGuard,
    generic tun/tap, PPP). These legitimately have no gateway IP -- there's
    no "router" to speak of, traffic just goes down the tunnel -- so a
    missing gateway here is expected, not a sign the local network is down.
    """
    if not iface:
        return False
    lower = iface.lower()
    return lower.startswith(("utun", "tun", "tap", "ppp", "wg", "tailscale", "ipsec"))


def _iface_type_macos(iface: Optional[str]) -> str:
    if not iface:
        return "unknown"
    if _is_tunnel_iface(iface):
        return "VPN/Tunnel"
    rc, out, _ = run_cmd(["networksetup", "-listallhardwareports"])
    if rc != 0:
        return "unknown"
    # Blocks look like:
    #   Hardware Port: Wi-Fi
    #   Device: en0
    #   Ethernet Address: ...
    blocks = out.split("\n\n")
    for block in blocks:
        dev_match = re.search(r"Device:\s*(\S+)", block)
        port_match = re.search(r"Hardware Port:\s*(.+)", block)
        if dev_match and port_match and dev_match.group(1) == iface:
            port_name = port_match.group(1).strip()
            if "Wi-Fi" in port_name or "AirPort" in port_name:
                return "Wi-Fi"
            if "Ethernet" in port_name or "LAN" in port_name:
                return "Ethernet"
            return port_name
    return "unknown"


def _iface_type_linux(iface: Optional[str]) -> str:
    if not iface:
        return "unknown"
    if _is_tunnel_iface(iface):
        return "VPN/Tunnel"
    rc, _, _ = run_cmd(["test", "-d", f"/sys/class/net/{iface}/wireless"])
    # `test` isn't informative via run_cmd's captured output; check existence
    # directly instead.
    import os

    if os.path.isdir(f"/sys/class/net/{iface}/wireless"):
        return "Wi-Fi"
    if iface.startswith(("wl",)):
        return "Wi-Fi"
    if iface.startswith(("en", "eth", "eno", "enp")):
        return "Ethernet"
    return "unknown"


def _dns_servers_macos() -> List[str]:
    rc, out, _ = run_cmd(["scutil", "--dns"])
    servers = []
    if rc == 0:
        servers = re.findall(r"nameserver\[\d+\]\s*:\s*(\S+)", out)
    if servers:
        # de-dup, keep order
        seen = []
        for s in servers:
            if s not in seen:
                seen.append(s)
        return seen
    return _dns_servers_resolv_conf()


def _dns_servers_linux() -> List[str]:
    servers = _dns_servers_resolv_conf()
    if servers:
        return servers
    rc, out, _ = run_cmd(["nmcli", "dev", "show"])
    if rc == 0:
        return re.findall(r"IP4\.DNS\[\d+\]:\s*(\S+)", out)
    return []


def _dns_servers_resolv_conf() -> List[str]:
    try:
        with open("/etc/resolv.conf") as f:
            content = f.read()
        return re.findall(r"nameserver\s+(\S+)", content)
    except OSError:
        return []


def _windows_ipconfig_all() -> str:
    rc, out, _ = run_cmd(["ipconfig", "/all"])
    return out if rc == 0 else ""


_WINDOWS_ADAPTER_HEADER_RE = re.compile(r"^\S.*\badapter\s+(.+):\s*$", re.IGNORECASE)
# Matches a real assigned "IPv4 Address" line but not the "Autoconfiguration
# IPv4 Address" (APIPA, 169.254.x.x) line Windows prints for an adapter that
# is up but never actually got a tunnel/DHCP address.
_WINDOWS_REAL_IPV4_RE = re.compile(r"^\s*IPv4 Address[ .]*:\s*(\S+)")


def _default_iface_windows(ipconfig_out: str) -> Optional[str]:
    # Real `ipconfig /all` output always inserts a blank line between an
    # adapter's "... adapter Name:" header and its own property lines
    # (Default Gateway included), so splitting on blank lines never keeps a
    # header and its gateway in the same chunk. Scan line-by-line instead,
    # attributing each property line to whichever header line most recently
    # preceded it. Also prefer a VPN/tunnel adapter (Tailscale, WireGuard,
    # ...) if one is present, even though it typically reports its "gateway"
    # oddly (or not at all) since those clients route via OS route-table
    # entries rather than a classic gateway.
    #
    # A tunnel adapter's virtual NIC persists in `ipconfig /all` even when
    # the client is fully disconnected (e.g. Tailscale not logged into a
    # tailnet) -- in that state it only has an APIPA "Autoconfiguration
    # IPv4 Address" and no gateway. Name matching alone would misreport that
    # as an active VPN, so also require a real assigned IPv4 address before
    # trusting it as the current interface.
    tunnel_iface = None
    tunnel_candidate = None
    gateway_iface = None
    current_name = None
    for line in ipconfig_out.splitlines():
        header_match = _WINDOWS_ADAPTER_HEADER_RE.match(line)
        if header_match:
            current_name = header_match.group(1).strip()
            if tunnel_candidate is None and _is_tunnel_iface_windows(current_name):
                tunnel_candidate = current_name
            continue
        if (
            tunnel_iface is None
            and tunnel_candidate == current_name
            and _WINDOWS_REAL_IPV4_RE.match(line)
        ):
            tunnel_iface = current_name
        if (
            current_name is not None
            and gateway_iface is None
            and re.search(r"Default Gateway[ .]*:\s*(\S+)", line)
        ):
            gateway_iface = current_name
    return tunnel_iface or gateway_iface


def _gateway_windows(ipconfig_out: str) -> Optional[str]:
    m = re.search(r"Default Gateway[ .]*:\s*(\d+\.\d+\.\d+\.\d+)", ipconfig_out)
    return m.group(1) if m else None


def _is_tunnel_iface_windows(iface_name: Optional[str]) -> bool:
    if not iface_name:
        return False
    lower = iface_name.lower()
    return any(
        k in lower
        for k in ("tailscale", "wireguard", "tap-windows", "tap ", "vpn", "point-to-point", "ppp")
    )


def _iface_type_windows(iface_name: Optional[str]) -> str:
    if not iface_name:
        return "unknown"
    if _is_tunnel_iface_windows(iface_name):
        return "VPN/Tunnel"
    lower = iface_name.lower()
    if "wi-fi" in lower or "wireless" in lower or "wlan" in lower:
        return "Wi-Fi"
    if "ethernet" in lower or "lan" in lower:
        return "Ethernet"
    return "unknown"


def _dns_servers_windows(ipconfig_out: str) -> List[str]:
    servers = []
    lines = ipconfig_out.splitlines()
    capture = False
    for line in lines:
        if "DNS Servers" in line:
            m = re.search(r":\s*(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                servers.append(m.group(1))
            capture = True
            continue
        if capture:
            m = re.match(r"^\s*(\d+\.\d+\.\d+\.\d+)\s*$", line)
            if m:
                servers.append(m.group(1))
            else:
                capture = False
    seen = []
    for s in servers:
        if s not in seen:
            seen.append(s)
    return seen


def get_network_summary() -> Dict:
    """Best-effort snapshot of the current network connection."""
    iface = None
    iface_type = "unknown"
    gateway = None
    dns_servers: List[str] = []
    is_tunnel = False

    if SYSTEM == "Darwin":
        iface = _default_iface_macos()
        iface_type = _iface_type_macos(iface)
        gateway = _gateway_macos()
        dns_servers = _dns_servers_macos()
        is_tunnel = _is_tunnel_iface(iface)
    elif SYSTEM == "Linux":
        iface = _default_iface_linux()
        iface_type = _iface_type_linux(iface)
        gateway = _gateway_linux()
        dns_servers = _dns_servers_linux()
        is_tunnel = _is_tunnel_iface(iface)
    elif SYSTEM == "Windows":
        ipconfig_out = _windows_ipconfig_all()
        iface = _default_iface_windows(ipconfig_out)
        iface_type = _iface_type_windows(iface)
        gateway = _gateway_windows(ipconfig_out)
        dns_servers = _dns_servers_windows(ipconfig_out)
        is_tunnel = _is_tunnel_iface_windows(iface)

    return {
        "platform": SYSTEM,
        "interface": iface,
        "connection_type": iface_type,
        "local_ip": get_local_ip(),
        "gateway": gateway,
        "dns_servers": dns_servers,
        "is_tunnel": is_tunnel,
    }
