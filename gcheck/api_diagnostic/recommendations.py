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

"""Turn a failed API test into a human diagnosis + concrete fix steps, and
provide the easy steps for getting a Gemini API key in the first place.

Unlike the raw check names/details from `network_check` (which mirror the
standalone CLI tool's own output on purpose, see app.py), this diagnosis is
curated, user-facing prose -- the same kind of content as gcheck's own
network-diagnosis recommendations, which are fully localized. So this one is
too, via gcheck's `t()`. URLs and Google's own raw error/quota identifiers
(model names, quota metrics) are left as-is in any language.
"""

from typing import List, Optional, Tuple

from . import error_details
from .models import ApiTestResult
from ..i18n import t

AI_STUDIO_KEYS_URL = "https://aistudio.google.com/app/apikey"
RATE_LIMITS_DOCS = "https://ai.google.dev/gemini-api/docs/rate-limits"
QUOTAS_URL = "https://console.cloud.google.com/iam-admin/quotas"
BILLING_URL = "https://console.cloud.google.com/billing"
ENABLE_API_URL = "https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com"
AVAILABLE_REGIONS_URL = "https://ai.google.dev/gemini-api/docs/available-regions"
CLOUD_STATUS_URL = "https://status.cloud.google.com/"

# HTTP statuses and canonical gRPC-style status strings that mean "the request
# reached Google fine, but its server had a transient problem, and retrying is
# actually the fix" -- distinct from NETWORK_ERROR/TIMEOUT/TLS_ERROR below
# (which mean Google was never reached at all).
#
# 409 and 501 are deliberately NOT matched by bare HTTP code: HTTP 409 covers
# both ABORTED (a concurrency conflict -- retry is correct) and ALREADY_EXISTS
# (the entity already exists -- retrying changes nothing), and 501 means
# UNIMPLEMENTED (the operation/feature isn't supported at all -- retrying
# won't help either). Only the genuinely retryable statuses are listed, so
# ALREADY_EXISTS/UNIMPLEMENTED/CANCELLED fall through to the generic fallback
# instead of being told to "wait and retry".
_TRANSIENT_HTTP = {408, 500, 503, 504}
_TRANSIENT_STATUS = {"ABORTED", "DEADLINE_EXCEEDED", "INTERNAL", "UNAVAILABLE"}

# Keywords that show up in Google's own FAILED_PRECONDITION message text when
# it's actually about the caller's geographic location, as opposed to some
# other unmet prerequisite (e.g. billing not enabled at all) that also comes
# back as FAILED_PRECONDITION -- see `recommend()` below.
_LOCATION_KEYWORDS = ("location", "country", "territory", "region")

# Keywords in Google's own message when a key was auto-revoked for being
# publicly exposed (e.g. committed to a public repo, pasted in a public gist)
# -- checked against the raw English text, which doesn't change with the UI
# language. This is a different situation from a merely mistyped/expired key:
# the key is compromised, so the fix is "rotate it", not just "get a new one".
_LEAKED_KEY_KEYWORDS = ("leak", "expos", "publicly available", "publicly accessible")


def _project_link(base: str, project: Optional[str]) -> str:
    """Append ``?project=…`` to a console URL when the project is known."""
    if not project:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}project={project}"


def recommend(result: ApiTestResult) -> Tuple[str, List[str]]:
    """Return ``(title, steps)`` describing why a test failed and how to fix it."""
    status = (result.error_status or "").upper()
    code = (result.error_code or "").upper()
    http = result.http_status

    # ── Key was publicly exposed and auto-revoked ───────────────────────────
    # Checked first: this can otherwise present as an ordinary 400 invalid-key
    # or 403 permission-denied error, but the fix is different -- the key is
    # compromised and must be rotated, not just replaced with a lookalike.
    if _looks_like_leaked_key_issue(result):
        return (
            t("api_rec_leaked_title"),
            [
                t("api_rec_leaked_1"),
                t("api_rec_leaked_2"),
                t("api_rec_leaked_3", url=AI_STUDIO_KEYS_URL),
                t("api_rec_leaked_4"),
            ],
        )

    # ── Bad / malformed / wrong key ────────────────────────────────────────
    if code == "API_KEY_INVALID" or (http == 400 and status == "INVALID_ARGUMENT"):
        return (
            t("api_rec_invalid_title"),
            [
                t("api_rec_invalid_1"),
                t("api_rec_invalid_2", url=AI_STUDIO_KEYS_URL),
                t("api_rec_invalid_3"),
                t("api_rec_invalid_4"),
                t("api_rec_invalid_5"),
            ],
        )

    # ── Region / location restricted ───────────────────────────────────────
    # Google gates the Gemini API by the caller's apparent geographic location
    # (IP-based), independent of the key itself -- same key, different
    # network, different result. Comes back as 400 FAILED_PRECONDITION with
    # one of two distinct messages: the API isn't offered at all here, or only
    # the free tier isn't (paid tier would still work).
    #
    # FAILED_PRECONDITION is also Google's generic "some other prerequisite
    # isn't met" status (e.g. billing not enabled at all) -- unrelated to
    # location. Only claim this is a location problem when the message
    # actually says so; otherwise fall through to the checks below (and
    # ultimately the fallback), rather than guessing wrong.
    if status == "FAILED_PRECONDITION":
        text = (result.message or "").lower()
        if "free tier" in text:
            return (
                t("api_rec_location_freetier_title"),
                [
                    t("api_rec_location_freetier_1"),
                    t("api_rec_location_freetier_2", url=AI_STUDIO_KEYS_URL),
                    t("api_rec_location_3", url=AVAILABLE_REGIONS_URL),
                ],
            )
        if any(kw in text for kw in _LOCATION_KEYWORDS):
            return (
                t("api_rec_location_title"),
                [
                    t("api_rec_location_1"),
                    t("api_rec_location_2"),
                    t("api_rec_location_3", url=AVAILABLE_REGIONS_URL),
                ],
            )

    # ── Credential not accepted as an API key ──────────────────────────────
    # A malformed/wrong key (notably the newer AQ. format) comes back as
    # 401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED rather than 400.
    if http == 401 or status == "UNAUTHENTICATED" or code == "ACCESS_TOKEN_TYPE_UNSUPPORTED":
        return (
            t("api_rec_bad_cred_title"),
            [
                t("api_rec_bad_cred_1"),
                t("api_rec_bad_cred_2"),
                t("api_rec_bad_cred_3", url=AI_STUDIO_KEYS_URL),
                t("api_rec_bad_cred_4"),
                t("api_rec_bad_cred_5"),
            ],
        )

    # ── Key valid but not permitted ────────────────────────────────────────
    if http == 403 or status == "PERMISSION_DENIED" or code in {"SERVICE_DISABLED", "PERMISSION_DENIED"}:
        det = error_details.details_from_result_data(result.data)
        # A disabled service returns a direct one-click activation URL and the
        # project number — far more actionable than the generic library link.
        enable_url = det.activation_url or _project_link(ENABLE_API_URL, det.project_number)
        proj = t("api_rec_permission_proj_suffix", number=det.project_number) if det.project_number else ""
        steps = [
            t("api_rec_permission_1", proj=proj),
            f"  {enable_url}",
            t("api_rec_permission_2"),
            t("api_rec_permission_3"),
            t("api_rec_permission_4", url=AI_STUDIO_KEYS_URL),
        ]
        return t("api_rec_permission_title"), steps

    # ── Rate / quota limits ────────────────────────────────────────────────
    if http == 429 or status == "RESOURCE_EXHAUSTED":
        return _recommend_quota(result)

    # ── Model not found ────────────────────────────────────────────────────
    if http == 404 or status == "NOT_FOUND":
        return (
            t("api_rec_model_notfound_title"),
            [
                t("api_rec_model_notfound_1"),
                t("api_rec_model_notfound_2"),
                t("api_rec_model_notfound_3"),
            ],
        )

    # ── Operation/feature not supported ─────────────────────────────────────
    # Distinct from "model not found" (404): the model/API exists, but the
    # specific operation being called isn't implemented for it. Not a key
    # problem, and unlike the transient errors below, retrying won't help.
    if http == 501 or status == "UNIMPLEMENTED":
        return (
            t("api_rec_unimplemented_title"),
            [
                t("api_rec_unimplemented_1"),
                t("api_rec_unimplemented_2"),
            ],
        )

    # ── Transient server-side error (retry, not a key problem) ─────────────
    # The request reached Google fine and got a real response -- its server
    # just had a temporary problem handling it. Different from
    # NETWORK_ERROR/TIMEOUT/TLS_ERROR below, where Google was never reached.
    if http in _TRANSIENT_HTTP or status in _TRANSIENT_STATUS:
        return (
            t("api_rec_transient_title"),
            [
                t("api_rec_transient_1"),
                t("api_rec_transient_2"),
                t("api_rec_transient_3", url=CLOUD_STATUS_URL),
            ],
        )

    # ── Local trust store can't verify Google's certificate ────────────────
    if status == "TLS_CERT_ERROR":
        return (
            t("api_rec_tls_cert_title"),
            [
                t("api_rec_tls_cert_1"),
                t("api_rec_tls_cert_2"),
                t("api_rec_tls_cert_3"),
                "  /Applications/Python\\ 3.12/Install\\ Certificates.command",
                t("api_rec_tls_cert_4"),
                "  python3 -m pip install --upgrade certifi",
                t("api_rec_tls_cert_5"),
            ],
        )

    # ── Never reached Google (DNS / connection / TLS / timeout) ────────────
    if status in {"NETWORK_ERROR", "TIMEOUT", "TLS_ERROR"}:
        return (
            t("api_rec_network_title"),
            [
                t("api_rec_network_1"),
                t("api_rec_network_2", url=AVAILABLE_REGIONS_URL),
                t("api_rec_network_3"),
                t("api_rec_network_4"),
            ],
        )

    # ── Fallback ───────────────────────────────────────────────────────────
    # (the raw HTTP/status/message detail is already shown separately above
    # this recommendation -- see ApiKeyTestScreen -- so it isn't repeated here.)
    return t("api_rec_fallback_title"), [t("api_rec_fallback_1", url=AI_STUDIO_KEYS_URL)]


def _looks_like_billing_issue(result: ApiTestResult, det) -> bool:
    """True when a 429 is really a billing/credits problem, not a rate limit.

    Checked against Google's own raw error message, which is always English
    regardless of the UI language.
    """
    text = (result.message or "").lower()
    if any(kw in text for kw in ("prepay", "credit", "depleted", "billing", "balance", "payment")):
        return True
    return any("billing" in url.lower() for _, url in det.help_links)


def is_billing_issue(result: ApiTestResult) -> bool:
    """Public: does this failure look like a paid-tier billing/credits problem?"""
    det = error_details.details_from_result_data(result.data)
    return _looks_like_billing_issue(result, det)


def _looks_like_leaked_key_issue(result: ApiTestResult) -> bool:
    """True when the key was auto-revoked for being publicly exposed."""
    text = (result.message or "").lower()
    return any(kw in text for kw in _LEAKED_KEY_KEYWORDS)


# finishReason/blockReason values from a *successful* generateContent call
# that produced no text, mapped to a short, actionable note -- distinct from
# recommend() above, which is only for HTTP-level/network failures. SAFETY,
# PROHIBITED_CONTENT, SPII and BLOCKLIST all mean the same thing in practice
# (Google's content filters withheld the reply), so they share one message;
# see gemini.block_reason() for where these values come from.
_BLOCK_REASON_TIP_KEYS = {
    "SAFETY": "api_block_tip_safety",
    "PROHIBITED_CONTENT": "api_block_tip_safety",
    "SPII": "api_block_tip_safety",
    "BLOCKLIST": "api_block_tip_safety",
    "RECITATION": "api_block_tip_recitation",
    "LANGUAGE": "api_block_tip_language",
}
_BLOCK_REASON_TIP_DEFAULT = "api_block_tip_default"


def block_reason_tip(reason: str) -> str:
    """A short note on why a blocked generateContent reply isn't a key problem."""
    key = _BLOCK_REASON_TIP_KEYS.get((reason or "").upper(), _BLOCK_REASON_TIP_DEFAULT)
    return t(key)


def _recommend_quota(result: ApiTestResult) -> Tuple[str, List[str]]:
    """Narrow diagnosis for a 429, driven by the structured QuotaFailure details."""
    det = error_details.details_from_result_data(result.data)
    q = det.quota

    # A 429 can also mean "paid-tier billing is blocking you" (e.g. prepay
    # credits depleted) rather than a rate limit — waiting would be useless.
    if _looks_like_billing_issue(result, det):
        steps = [
            t("api_rec_billing_1"),
            t("api_rec_billing_2"),
            t("api_rec_billing_3", url="https://aistudio.google.com/"),
            t("api_rec_billing_4", url="https://aistudio.google.com/"),
            t("api_rec_billing_5", url="https://ai.google.dev/gemini-api/docs/billing"),
        ]
        for desc, url in det.help_links:
            steps.append(f"{desc}: {url}")
        return t("api_rec_billing_title"), steps

    # No structured details — fall back to the generic guidance.
    if q is None:
        steps = [
            t("api_rec_quota_generic_1"),
            t("api_rec_quota_generic_2"),
            t("api_rec_quota_generic_3", url=QUOTAS_URL),
            t("api_rec_quota_generic_4", url=RATE_LIMITS_DOCS),
        ]
        return t("api_rec_quota_generic_title"), steps

    # Build a specific title from a single, fully-composed phrase per
    # daily/per-minute + free-tier combination. (A fragment-concatenation
    # approach was tried here before, but word-order differs across
    # languages — e.g. Spanish puts the noun before its modifiers — so
    # naively joined fragments produced ungrammatical text in some locales.)
    if q.is_per_day:
        combo = "daily_freetier" if q.is_free_tier else "daily"
    elif q.is_per_minute:
        combo = "perminute_freetier" if q.is_free_tier else "perminute"
    elif q.is_free_tier:
        combo = "freetier"
    else:
        combo = "base"
    title = t(f"api_rec_quota_phrase_{combo}")
    title = title[0].upper() + title[1:]
    if q.model:
        title += t("api_rec_quota_word_formodel", model=q.model)
    title += t("api_rec_quota_period")

    steps: List[str] = [t("api_rec_quota_detail_1")]
    if q.value:
        if q.quota_id:
            steps.append(t("api_rec_quota_limit_hit_with_id", value=q.value, quota_id=q.quota_id))
        else:
            steps.append(t("api_rec_quota_limit_hit", value=q.value))

    # Wait guidance — report only, never auto-retry.
    if q.is_per_day:
        steps.append(t("api_rec_quota_daily_wait_1"))
        steps.append(t("api_rec_quota_daily_wait_2"))
    elif det.retry_delay_seconds is not None:
        steps.append(t("api_rec_quota_retry_delay", seconds=f"{det.retry_delay_seconds:.0f}"))
    elif q.is_per_minute:
        steps.append(t("api_rec_quota_perminute_wait"))

    # Where to fix it, narrowed by tier.
    if q.is_free_tier:
        steps.append(t("api_rec_quota_freetier_fix_1"))
        steps.append(f"  {_project_link(BILLING_URL, det.project_number)}")
    else:
        steps.append(t("api_rec_quota_paidtier_fix_1"))
        steps.append(f"  {_project_link(QUOTAS_URL, det.project_number)}")

    for desc, url in det.help_links:
        steps.append(f"{desc}: {url}")
    if not det.help_links:
        steps.append(t("api_rec_quota_reference", url=RATE_LIMITS_DOCS))

    return title, steps


def steps_to_get_key() -> List[str]:
    """The easiest way to obtain a Gemini API key, as ordered steps."""
    return [
        f"Open Google AI Studio:  {AI_STUDIO_KEYS_URL}",
        "Sign in with your Google account (any personal Gmail works).",
        "Click 'Create API key' (choose or create a project if prompted).",
        "Copy the key it shows — new keys start with 'AQ.'.",
        "Paste it here, or save it in a .env file as:  GEMINI_API_KEY=your_key",
    ]
