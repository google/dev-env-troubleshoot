# gcheck unit tests

Unit tests for `gcheck`, using `pytest`. This is a separate, git-visible
folder (unlike `test/`, which is git-ignored local eval transcripts) so it
ships to GitHub and runs in CI.

No real network, filesystem-outside-`tmp_path`, or subprocess calls happen
anywhere in this suite — everything's mocked. Safe to run offline, repeatedly.

## Run it

```sh
pip install -e ".[test]"                                # once, from repo root
pytest unit_test                                        # run everything
pytest unit_test -v                                      # verbose
pytest unit_test -k scanner                              # filter by name
pytest unit_test --cov=gcheck --cov-report=term-missing  # with coverage
```

## What's covered

**232 tests** (231 passed, 1 skipped — see [Gotchas](#gotchas)), mirroring `gcheck/`'s package layout:

| Test file | # | Covers |
|---|---|---|
| **`unit_test/`** | | |
| `test_i18n.py` | 12 | `t()` / `set_language()` / `detect_language()`, locale fallback |
| `test_self_install.py` | 7 | platform/frozen dispatch, Windows PATH-registry append |
| `test_diagnosis_i18n.py` | 6 | every `diagnose()` branch |
| `test_diagnostics.py` | 5 | `run_diagnostics()` orchestration, notice dedup |
| `test_recommendations.py` | 4 | `build_diagnosis()` region-hint logic |
| `test_main.py` | 4 | CLI: `install` subcommand, default launch, `--lang` |
| `test_gate.py` | 4 | `check_gate()` success/timeout/refused |
| `test_app.py` | 3 | app boot routing, title/theme |
| `test_code_setup.py` | 1 | `find_api_keys()` delegation |
| **`api_diagnostic/`** | | |
| `test_recommendations.py` | 27 | every `recommend()` branch (invalid/leaked key, region lock, quota/billing, transient, TLS, fallback) |
| `test_gemini_request.py` | 25 | Gemini HTTP client — success/error/TLS-retry (mocked `urlopen`) |
| `test_error_details.py` | 18 | Google `error.details[]` parsing |
| `test_gemini.py` | 16 | response-parsing helpers |
| `test_scanner.py` | 14 | key regex/placeholder detection, directory walk |
| `test_models.py` | 4 | dataclasses |
| **`network_check/`** | | |
| `test_utils.py` | 21 | TCP/HTTP/DNS probes, TLS-fallback retry |
| `test_netinfo.py` | 21 | Win/macOS/Linux network-info parsers (real captured sample output) |
| `test_connectivity.py` | 10 | gateway/site checks |
| `test_models.py` | 3 | `CheckResult` dataclass |
| `test_google_check.py` | 2 | domain list composition |
| **`ui/screens/`** (Textual `Pilot`) | | |
| `test_api_finding_screen.py` | 10 | key-found states, masking, timeout/scan-error fallback |
| `test_api_key_test_screen.py` | 8 | success, every failure path, block handling, buttons |
| `test_language_screen.py` | 5 | card selection, grid nav |
| `test_trust_screen.py` | 2 | allow/deny |

**Not covered, on purpose:** `app.py`'s clipboard/signal/screenshot internals
(side-effect-heavy, low test value); a few defensive `except BaseException`
fallbacks.

## Gotchas

- **i18n is global state.** `t()` returns the raw key until `set_language()`
  runs; `conftest.py` resets it around every test.
- **Don't touch the real `.env`/`GEMINI_API_KEY`.** Screens set it directly
  via `os.environ`, not `monkeypatch` — restore it by hand if you touch it.
- **Mock a worker's data source before pushing its screen**, then
  `await app.workers.wait_for_complete()` (+ `pilot.pause()`) before asserting.
- **Use `Button.press()`, not `pilot.click()`**, for buttons that might sit
  below the 80x24 test-viewport fold — `click()` raises `OutOfBounds` off-screen.
- **The symlink test self-skips** without symlink privilege (default on
  Windows) — enable Developer Mode or run elevated to actually exercise it.
