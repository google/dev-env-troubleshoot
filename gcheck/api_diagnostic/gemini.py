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

"""Test a Gemini API key against Google's Generative Language API.

Two calls, both over the standard library only:

* ``list_models``  -- ``GET  /v1beta/models``   (cheap, validates the key)
* ``generate``     -- ``POST /v1beta/models/{model}:generateContent``

Neither raises: every outcome (HTTP error, DNS failure, timeout, TLS error) is
turned into an :class:`ApiTestResult` so the caller can render a recommendation.
"""

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .models import ApiTestResult

BASE = "https://generativelanguage.googleapis.com/v1beta"
USER_AGENT = "gcheck/0.1 (+gemini key tester)"
DEFAULT_TIMEOUT = 15.0

# Preference order when picking a model for the generate step.
_PREFERRED_MODELS = ("gemini-1.5-flash", "gemini-flash-latest", "gemini-1.5-flash-latest")

# Known-good CA bundle locations to fall back on when the interpreter's own
# default trust store is empty/broken -- the classic python.org macOS installer
# trap where TLS verification fails with CERTIFICATE_VERIFY_FAILED even though
# the network is fine. See ``_find_fallback_cafile``.
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
    """Locate a usable CA bundle outside the interpreter's default trust store."""
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


def _is_cert_verify_error(exc: BaseException) -> bool:
    """True if ``exc`` (possibly wrapped in a URLError) is a cert-verify failure."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(reason)


def _ssl_contexts() -> List[ssl.SSLContext]:
    """Contexts to try in order: the default, then a fallback CA bundle if found."""
    contexts = [ssl.create_default_context()]
    cafile = _find_fallback_cafile()
    if cafile:
        contexts.append(ssl.create_default_context(cafile=cafile))
    return contexts


def _request(
    url: str,
    stage: str,
    *,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ApiTestResult:
    """Perform one request and normalise the result into an ApiTestResult."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        # Pass the key as a header, not a ?key= query param, so the secret
        # stays out of the URL -- and therefore out of any proxy/error
        # logging that records URLs but not headers.
        headers["x-goog-api-key"] = api_key
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    # Try the default trust store first; if it can't verify Google's cert (an
    # empty/broken local store, not a real block), retry once with a known-good
    # CA bundle found elsewhere on the system.
    contexts = _ssl_contexts()
    last_cert_error: Optional[BaseException] = None

    for ctx in contexts:
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return ApiTestResult(ok=True, stage=stage, http_status=resp.status, data=payload)

        except urllib.error.HTTPError as exc:
            # Google returns a JSON error body: {"error": {"code", "status", "message", "details":[{"reason"}]}}
            status = error_code = None
            message = f"HTTP {exc.code}"
            err: Dict[str, Any] = {}
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                err = payload.get("error", {}) if isinstance(payload, dict) else {}
                status = err.get("status")
                message = err.get("message", message)
                for detail in err.get("details", []) or []:
                    if isinstance(detail, dict) and detail.get("reason"):
                        error_code = detail["reason"]
                        break
            except (ValueError, OSError):
                pass
            return ApiTestResult(
                ok=False,
                stage=stage,
                http_status=exc.code,
                error_status=status,
                error_code=error_code,
                message=message,
                # Keep the raw error object so recommendations can parse the
                # structured details[] (QuotaFailure, RetryInfo, ErrorInfo, …).
                data={"error": err},
            )

        except (socket.timeout, TimeoutError):
            return ApiTestResult(
                ok=False, stage=stage, error_status="TIMEOUT",
                message=f"Request to Google timed out after {timeout:.0f}s.",
            )
        except (urllib.error.URLError, ssl.SSLError, OSError) as exc:
            if _is_cert_verify_error(exc):
                last_cert_error = exc
                continue  # retry with the next (fallback CA bundle) context
            if isinstance(exc, ssl.SSLError):
                return ApiTestResult(
                    ok=False, stage=stage, error_status="TLS_ERROR",
                    message=f"TLS error talking to Google: {exc}",
                )
            # DNS failure / connection refused / reset — never reached Google.
            reason = getattr(exc, "reason", exc)
            return ApiTestResult(
                ok=False, stage=stage, error_status="NETWORK_ERROR",
                message=f"Could not reach Google: {reason}",
            )
        except ValueError as exc:
            return ApiTestResult(
                ok=False, stage=stage, error_status="NETWORK_ERROR",
                message=f"Unexpected error contacting Google: {exc}",
            )

    # Every context failed certificate verification.
    return ApiTestResult(
        ok=False, stage=stage, error_status="TLS_CERT_ERROR",
        message=f"TLS certificate verification failed: {getattr(last_cert_error, 'reason', last_cert_error)}",
    )


def list_models(api_key: str, timeout: float = DEFAULT_TIMEOUT) -> ApiTestResult:
    """Validate the key by listing available models."""
    return _request(f"{BASE}/models", "list_models", api_key=api_key, timeout=timeout)


def generate(
    api_key: str, model: str, timeout: float = DEFAULT_TIMEOUT, prompt: str = "Say hi in 3 words."
) -> ApiTestResult:
    """Confirm generation works by sending a minimal prompt."""
    model_path = model if model.startswith("models/") else f"models/{model}"
    url = f"{BASE}/{model_path}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    return _request(url, "generate", method="POST", body=body, api_key=api_key, timeout=timeout)


def model_names(list_result: ApiTestResult) -> List[str]:
    """Extract bare model names from a successful list_models result."""
    names = []
    for m in list_result.data.get("models", []) or []:
        # A non-standard proxy / AI gateway can return `models` as a list of
        # bare strings instead of Google's list of objects -- calling .get on
        # those would raise AttributeError and crash the caller.
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        if not isinstance(name, str):
            continue
        if name:
            names.append(name.split("/", 1)[-1] if name.startswith("models/") else name)
    return names


def pick_generate_model(list_result: ApiTestResult) -> Optional[str]:
    """Choose a model that supports generateContent, preferring a flash model."""
    models = list_result.data.get("models", []) or []

    supports = {}
    for m in models:
        # Tolerate a non-standard schema (e.g. a proxy returning `models` as a
        # list of strings): skip anything that isn't Google's object shape
        # rather than letting .get raise AttributeError up into the worker.
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        if not isinstance(name, str):
            name = ""
        bare = name.split("/", 1)[-1] if name.startswith("models/") else name
        methods = m.get("supportedGenerationMethods") or []
        if not isinstance(methods, (list, tuple)):
            methods = []
        if bare and "generateContent" in methods:
            supports[bare] = True

    for preferred in _PREFERRED_MODELS:
        if preferred in supports:
            return preferred
    return next(iter(supports), None)


def reply_text(generate_result: ApiTestResult) -> str:
    """Pull the model's text reply out of a generateContent response."""
    candidates = generate_result.data.get("candidates", []) or []
    if not isinstance(candidates, list):
        return ""
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        # On a safety/recitation block the candidate often carries an explicit
        # "content": null (not a missing key), so `.get("content", {})` returns
        # None, not {} -- guard every level rather than chaining .get straight
        # through and raising 'NoneType' has no attribute 'get'.
        content = cand.get("content") or {}
        if not isinstance(content, dict):
            continue
        parts = content.get("parts") or []
        if not isinstance(parts, list):
            continue
        text = "".join(
            p.get("text", "") for p in parts if isinstance(p, dict)
        ).strip()
        if text:
            return text
    return ""


# finishReason values that just mean "the model stopped normally", as opposed
# to content actually being withheld -- everything else (SAFETY, RECITATION,
# LANGUAGE, PROHIBITED_CONTENT, SPII, BLOCKLIST, OTHER, IMAGE_*, ...) means the
# candidate was blocked, which is why reply_text() came back empty.
_NORMAL_FINISH_REASONS = {"STOP", "MAX_TOKENS"}


def block_reason(generate_result: ApiTestResult) -> Optional[str]:
    """When a successful generateContent call yields no text, say why.

    Returns Google's own ``blockReason``/``finishReason`` string (e.g.
    ``SAFETY``, ``RECITATION``, ``PROHIBITED_CONTENT``) or ``None`` if the
    call wasn't blocked -- e.g. it produced normal text, or genuinely stopped
    with no candidates for some other reason.
    """
    data = generate_result.data or {}
    feedback = data.get("promptFeedback") or {}
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        return feedback["blockReason"]
    candidates = data.get("candidates") or []
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        reason = candidates[0].get("finishReason")
        if reason and reason not in _NORMAL_FINISH_REASONS:
            return reason
    return None
