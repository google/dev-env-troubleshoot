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

"""Gateway reachability and general-internet baseline checks, independent of
Google.

Gateway check: is the default gateway even reachable (local network is up).
Baseline check: generally-unblocked, non-Google sites -- if these fail,
        either the local network/ISP is down, or the network is blocking
        general traffic broadly, not just Google -- a materially
        different problem than "just Google is down".

Each site is checked as a single unit (DNS + HTTPS GET) with a plain ok/fail
result -- no separate DNS/TCP/TLS/HTTP layer breakdown.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import List

from .data import GENERAL_BASELINE_DOMAINS
from .models import CheckResult
from .utils import http_get, resolve_system, tcp_connect

# gcheck integration note: sites are checked concurrently instead of
# network_check's original sequential list comprehension, to fit gcheck's
# interactive TUI diagnostic budget. Per-site timeouts are kept identical to
# network_check's own defaults (see below).


def check_gateway(gateway: str, is_tunnel: bool = False) -> CheckResult:
    if not gateway:
        if is_tunnel:
            return CheckResult(
                name="gateway",
                ok=True,
                detail="No gateway IP, but default route is a point-to-point VPN/tunnel "
                "interface -- this is expected and not a sign of a local network problem",
            )
        return CheckResult(name="gateway", ok=False, detail="No default gateway detected")
    result = tcp_connect(gateway, 80, timeout=3.0)
    # Many home routers don't listen on 80/443 at all; a refused connection
    # still proves the gateway is reachable at layer 3. Only timeout means
    # "couldn't even reach it."
    reachable = result["error"] != "timeout"
    detail = f"{gateway} " + ("reachable" if reachable else "unreachable (timeout)")
    return CheckResult(name="gateway", ok=reachable, detail=detail, latency_ms=result["latency_ms"])


def _check_site(domain: str) -> CheckResult:
    dns = resolve_system(domain, timeout=5.0)
    if not dns["ok"]:
        return CheckResult(name=domain, ok=False, detail=f"DNS failed: {dns['error']}")
    http = http_get(f"https://{domain}/", timeout=8.0)
    if http["ok"]:
        data = {"ips": dns["ips"]}
        if http.get("note_tags"):
            data["note_tags"] = http["note_tags"]
        return CheckResult(
            name=domain,
            ok=True,
            detail=f"reachable (HTTP {http['status']})",
            latency_ms=http["latency_ms"],
            data=data,
        )
    return CheckResult(
        name=domain,
        ok=False,
        detail=f"DNS ok ({dns['ips']}) but HTTPS failed: {http['error']}",
        latency_ms=http["latency_ms"],
        data={"ips": dns["ips"]},
    )


def check_sites(domains: List[str]) -> List[CheckResult]:
    """DNS + HTTPS GET against each domain, run concurrently."""
    if not domains:
        # ThreadPoolExecutor(max_workers=0) raises ValueError -- guard so an
        # empty domain list is just an empty result, not a crashed worker.
        return []
    with ThreadPoolExecutor(max_workers=len(domains)) as executor:
        return list(executor.map(_check_site, domains))


def check_general_baseline() -> List[CheckResult]:
    return check_sites(GENERAL_BASELINE_DOMAINS)
