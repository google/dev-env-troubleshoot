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

"""Low-level building blocks: subprocess, sockets, TLS (via HTTPS), DNS.

Kept to the standard library on purpose -- this tool needs to run in
environments where `pip install` itself may be slow or unreliable.
"""

import os
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Dict, List, Optional, Tuple

from .data import REQUEST_TIMEOUT

USER_AGENT = "network-checks/0.1 (+diagnostic tool)"

# Fallback CA bundle locations to try when the interpreter's own default
# trust store is empty. This is a real, common trap: the python.org macOS
# installer ships without a populated CA bundle until you run its
# "Install Certificates.command", so every TLS verification fails with
# CERTIFICATE_VERIFY_FAILED regardless of network conditions. Detecting and
# working around that here keeps a broken local Python from masquerading as
# a network filtering block.
_CA_BUNDLE_CANDIDATES = [
    "/etc/ssl/cert.pem",
    "/private/etc/ssl/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/usr/local/etc/openssl/cert.pem",
    "/usr/local/etc/openssl@1.1/cert.pem",
    "/opt/homebrew/etc/openssl@3/cert.pem",
]

_fallback_cafile_cache: Dict[str, Optional[str]] = {}


def _find_fallback_cafile() -> Optional[str]:
    if "path" in _fallback_cafile_cache:
        return _fallback_cafile_cache["path"]
    path = None
    try:
        import certifi

        path = certifi.where()
    except ImportError:
        for candidate in _CA_BUNDLE_CANDIDATES:
            if os.path.isfile(candidate):
                path = candidate
                break
    _fallback_cafile_cache["path"] = path
    return path


def build_ssl_context(cafile: Optional[str] = None, cap_tls12: bool = False) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=cafile)
    if cap_tls12:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def default_ssl_context() -> ssl.SSLContext:
    return build_ssl_context()


LOCAL_TRUST_STORE_HINT = (
    "Your Python interpreter's default certificate trust store appears to be empty or "
    "misconfigured (common with the python.org installer on macOS before running its "
    "'Install Certificates.command', found in the Python application folder) -- this is a "
    "local issue, not a network/firewall block. Fix it with that command, or `pip install "
    "certifi`, so future runs verify TLS correctly by default."
)

TLS13_STALL_HINT = (
    "TLS 1.3 handshake stalled against this server with this Python's TLS stack; succeeded "
    "once capped to TLS 1.2 -- likely a client/server negotiation quirk, not necessarily "
    "blocking."
)

# Maps a short tag to its explanatory message, so callers can dedupe by
# *cause* (a set of tags) instead of by exact composed sentence -- two
# checks can hit the same underlying issue but combine it with a different
# second issue, which would otherwise produce two distinct-looking strings
# for what is really one thing to tell the user.
NOTE_MESSAGES = {
    "local_trust_store": LOCAL_TRUST_STORE_HINT,
    "tls13_stall": TLS13_STALL_HINT,
}


def _layered_retry(attempt) -> Dict:
    """Try `attempt(ctx)` against progressively more permissive SSL contexts,
    to tell apart two common non-blocking failure modes from a genuine
    network/firewall problem before giving up:

    - handshake *timeout*: some TLS stacks' TLS 1.3 ClientHello stalls
      against a specific server; capping to TLS 1.2 tells that apart from
      an actual on-path block.
    - certificate *verification* failure: retried once against a
      known-good CA bundle found elsewhere on the system, to rule out an
      empty/broken local trust store before treating it as a real
      (possibly MITM) certificate problem.

    `attempt` takes an ssl.SSLContext and returns a dict with at least
    "ok" and "error_kind" ("timeout" | "cert_verify" | "other" | None).
    """
    result = attempt(build_ssl_context())
    if result["ok"]:
        return result

    cap = False
    note_tags: List[str] = []
    if result["error_kind"] == "timeout":
        capped = attempt(build_ssl_context(cap_tls12=True))
        if capped["ok"]:
            capped["note_tags"] = ["tls13_stall"]
            return capped
        if capped["error_kind"] == "cert_verify":
            result = capped
            cap = True
            note_tags.append("tls13_stall")
        # else: timed out (or failed some other way) at both TLS versions --
        # fall through keeping the original timeout result.

    if result["error_kind"] == "cert_verify":
        fallback_cafile = _find_fallback_cafile()
        if fallback_cafile is None:
            result["error"] = f"cert_verify_failed (no local trust store, no fallback found): {result['error']}"
            return result
        retry = attempt(build_ssl_context(cafile=fallback_cafile, cap_tls12=cap))
        if retry["ok"]:
            retry["note_tags"] = note_tags + ["local_trust_store"]
            return retry
        retry["error"] = f"cert_verify_failed even with a known-good CA bundle: {retry['error']}"
        return retry

    return result


def run_cmd(cmd: List[str], timeout: float = 5.0) -> Tuple[int, str, str]:
    """Run a subprocess command, returning (returncode, stdout, stderr).

    Never raises on the command failing or not existing -- callers should
    treat a nonzero/failed result as "could not determine" rather than a
    hard error, since this tool must degrade gracefully across platforms.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return -1, "", str(exc)


def tcp_connect(host: str, port: int, timeout: float = REQUEST_TIMEOUT) -> Dict:
    """Attempt a raw TCP connect and time it. Distinguishes timeout vs reset
    vs refused, which matters a lot for telling DNS-level failures apart
    from IP/TLS-level connection resets.
    """
    start = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        elapsed = (time.monotonic() - start) * 1000
        sock.close()
        return {"ok": True, "latency_ms": round(elapsed, 1), "error": None}
    except socket.timeout:
        elapsed = (time.monotonic() - start) * 1000
        return {"ok": False, "latency_ms": round(elapsed, 1), "error": "timeout"}
    except ConnectionResetError:
        elapsed = (time.monotonic() - start) * 1000
        return {"ok": False, "latency_ms": round(elapsed, 1), "error": "connection_reset"}
    except ConnectionRefusedError:
        elapsed = (time.monotonic() - start) * 1000
        return {"ok": False, "latency_ms": round(elapsed, 1), "error": "connection_refused"}
    except OSError as exc:
        elapsed = (time.monotonic() - start) * 1000
        return {"ok": False, "latency_ms": round(elapsed, 1), "error": str(exc)}


def _is_cert_verify_error(exc: Exception) -> bool:
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLCertVerificationError) or isinstance(exc, ssl.SSLCertVerificationError)


def _is_timeout_error(exc: Exception) -> bool:
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, (socket.timeout, TimeoutError)) or isinstance(exc, (socket.timeout, TimeoutError))


def _http_get_once(url: str, timeout: float, headers: Dict, ctx: ssl.SSLContext) -> Dict:
    req = urllib.request.Request(url, headers=headers)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(2048)
            elapsed = (time.monotonic() - start) * 1000
            return {
                "ok": True,
                "status": resp.status,
                "latency_ms": round(elapsed, 1),
                "error": None,
                "error_kind": None,
                "body_preview": body[:200].decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        elapsed = (time.monotonic() - start) * 1000
        # An HTTP error still means the connection + TLS + server round trip
        # worked -- that's a meaningfully different outcome from a network
        # failure, so treat 4xx/5xx as "reachable" for diagnostic purposes.
        return {"ok": True, "status": exc.code, "latency_ms": round(elapsed, 1), "error": None, "error_kind": None}
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as exc:
        elapsed = (time.monotonic() - start) * 1000
        reason = getattr(exc, "reason", exc)
        if _is_cert_verify_error(exc):
            kind = "cert_verify"
        elif _is_timeout_error(exc):
            kind = "timeout"
        else:
            kind = "other"
        return {"ok": False, "status": None, "latency_ms": round(elapsed, 1), "error": str(reason), "error_kind": kind}


def http_get(url: str, timeout: float = REQUEST_TIMEOUT, headers: Optional[Dict] = None) -> Dict:
    """Simple HTTP(S) GET, returning status/latency/error without raising.

    See `_layered_retry` for how timeout/cert-verify failures are told
    apart from a genuine block before giving up.
    """
    req_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    return _layered_retry(lambda ctx: _http_get_once(url, timeout, req_headers, ctx))


def resolve_system(hostname: str, timeout: float = REQUEST_TIMEOUT) -> Dict:
    """Resolve via the OS resolver (whatever /etc/resolv.conf or the
    platform's networking stack is configured to use).

    ``socket.getaddrinfo`` is a blocking C call that ``socket.setdefaulttimeout``
    does not actually bound, and mutating that process-global from these
    checks -- which run concurrently (see ``connectivity.check_sites``) --
    raced: one check's ``finally`` reset the timeout out from under a sibling
    still mid-lookup. So the lookup runs in its own throwaway thread instead
    and is abandoned (it unblocks and exits on its own shortly after) if it
    overruns ``timeout``; no global state is touched.
    """
    start = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(socket.getaddrinfo, hostname, None, socket.AF_INET)
        infos = future.result(timeout=timeout)
        elapsed = (time.monotonic() - start) * 1000
        ips = sorted({info[4][0] for info in infos})
        return {"ok": True, "ips": ips, "latency_ms": round(elapsed, 1), "error": None}
    except FuturesTimeoutError:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "ok": False, "ips": [], "latency_ms": round(elapsed, 1),
            "error": f"DNS lookup timed out after {timeout:.0f}s",
        }
    except (OSError, UnicodeError) as exc:
        # socket.gaierror is the common "name doesn't resolve" case, but it is
        # not the only failure getaddrinfo can raise: socket.herror (reverse
        # lookup / split-horizon DNS), socket.timeout / TimeoutError (a stalled
        # resolver), and bare OSError all escape a `except socket.gaierror`.
        # UnicodeError covers a hostname that can't be IDNA-encoded. Any of
        # these bubbling out crashes the diagnostic worker that called us and
        # wedges the UI on its spinner, so treat every one as "resolution
        # failed" and let the caller report it.
        elapsed = (time.monotonic() - start) * 1000
        return {"ok": False, "ips": [], "latency_ms": round(elapsed, 1), "error": str(exc)}
    finally:
        # wait=False: don't block on an overrunning getaddrinfo -- its worker
        # thread ends by itself once the call returns.
        executor.shutdown(wait=False)


