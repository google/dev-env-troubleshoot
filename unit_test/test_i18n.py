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

import pytest

import gcheck.i18n as i18n
from gcheck.i18n import detect_language, set_language, t


def test_t_returns_raw_key_when_nothing_loaded():
    assert t("app_name") == "app_name"


def test_t_unknown_key_returns_key_itself():
    assert t("this_key_does_not_exist") == "this_key_does_not_exist"


def test_t_formats_placeholders_after_language_loaded():
    set_language("en")
    assert t("diag_google_domain_failed", domain="x.com", detail="boom") == "x.com: boom"


def test_t_falls_back_to_unformatted_string_on_missing_kwargs():
    set_language("en")
    # diag_google_domain_failed expects domain/detail; omit them entirely.
    result = t("diag_google_domain_failed")
    assert result == "{domain}: {detail}"


def test_t_tolerates_no_kwargs_on_unloaded_key():
    # No set_language call: text == key, and .format(**kwargs) on a
    # plain key string (no placeholders) must not raise.
    assert t("api_rec_leaked_3", url="https://example.com") == "api_rec_leaked_3"


def test_set_language_unknown_lang_falls_back_to_english():
    set_language("fr")
    assert t("app_name") == "gcheck · Diagnostic Tool for Google AI Developers"


def test_set_language_supported_lang_loads_that_locale():
    set_language("es")
    assert t("app_name") != "app_name"
    assert i18n._strings.get("app_name") != "gcheck · Diagnostic Tool for Google AI Developers"


def test_detect_language_flag_takes_priority():
    assert detect_language("zh") == "zh"
    assert detect_language("ZH-CN") == "zh"


def test_detect_language_flag_unsupported_falls_back_to_english():
    assert detect_language("xx") == "en"


def test_detect_language_from_env_lang(monkeypatch):
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert detect_language() == "ja"


def test_detect_language_defaults_to_english_when_nothing_matches(monkeypatch):
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    assert detect_language() == "en"


def test_detect_language_locale_exception_is_swallowed(monkeypatch):
    monkeypatch.delenv("LANG", raising=False)

    def boom():
        raise ValueError("no locale")

    monkeypatch.setattr(i18n.locale, "getlocale", boom)
    assert detect_language() == "en"


def test_detect_language_from_posix_style_locale(monkeypatch):
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("es_ES", "UTF-8"))
    assert detect_language() == "es"


@pytest.mark.parametrize(
    ("locale_name", "expected"),
    [
        ("Chinese_China", "zh"),
        ("Spanish_Spain", "es"),
        ("Japanese_Japan", "ja"),
        ("English_United States", "en"),
    ],
)
def test_detect_language_from_windows_style_locale(monkeypatch, locale_name, expected):
    """Windows reports "Spanish_Spain", not "es_ES".

    Matching the two-letter code alone would regress zh/es to English here.
    """
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (locale_name, "1252"))
    assert detect_language() == expected
