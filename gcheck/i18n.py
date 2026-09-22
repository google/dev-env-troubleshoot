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

import json
import locale
import os
from pathlib import Path

_strings: dict = {}

LOCALES_DIR = Path(__file__).parent / "locales"

# Every language gcheck ships a locale file for. Anything outside this set is
# treated as "en" -- both so an unknown --lang is a no-op rather than an
# error, and so `lang` can never steer the open() below to an arbitrary path.
ALL_LANGS = ("en", "zh", "es", "ja")


def set_language(lang: str) -> None:
    global _strings
    if lang not in ALL_LANGS:
        lang = "en"
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        path = LOCALES_DIR / "en.json"
    with open(path, encoding="utf-8") as f:
        _strings = json.load(f)


def t(key: str, **kwargs) -> str:
    text = _strings.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # A locale string whose {placeholders} don't match the supplied
            # args must not crash the screen mid-render -- fall back to the
            # unformatted string. Shows up as a visible untranslated brace
            # rather than a traceback.
            pass
    return text


_SUPPORTED_LANGS = ("zh", "es", "ja")

# locale.getlocale() reports platform-native locale names, and they differ by
# OS: POSIX gives "es_ES", Windows gives "Spanish_Spain". Matching only the
# two-letter code would silently fall back to English for Spanish and Chinese
# Windows users, so accept both spellings.
_LOCALE_PREFIXES = {
    "zh": ("zh", "chinese"),
    "es": ("es", "spanish"),
    "ja": ("ja", "japanese"),
}


def _match_lang(value: str) -> str | None:
    """Map a locale string like "ja_JP.UTF-8" or "Japanese_Japan" to a code."""
    value = value.strip().lower()
    if not value:
        return None
    for lang in _SUPPORTED_LANGS:
        if value.startswith(_LOCALE_PREFIXES[lang]):
            return lang
    return None


def detect_language(flag_lang: str | None = None) -> str:
    if flag_lang:
        code = flag_lang.strip().lower()[:2]
        return code if code in ALL_LANGS else "en"

    match = _match_lang(os.environ.get("LANG", ""))
    if match:
        return match

    try:
        # getlocale() rather than getdefaultlocale(), which is deprecated
        # since 3.11 and slated for removal in 3.15.
        match = _match_lang(locale.getlocale()[0] or "")
        if match:
            return match
    except Exception:
        pass

    return "en"
