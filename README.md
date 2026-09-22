# gcheck CLI

gcheck CLI — a troubleshooting tool for Google developers. Diagnoses network issues accessing Google APIs, and can optionally verify a `GEMINI_API_KEY` against the Gemini API as a final connectivity check.

---

## Prerequisites

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/installation/) (recommended for install; not needed if using `pip` directly)
- A `GEMINI_API_KEY` (optional — only needed if you want to verify Gemini API connectivity)

---

## Install

### Quick install (recommended)

Clone the repo, then run the install script for your OS. It checks for
Python 3.10+ and `pipx` (installing either if missing) and installs
`gcheck` as a global, editable command — code edits apply immediately
without reinstalling:

```sh
# macOS / Linux
./install.sh
```

```powershell
# Windows (PowerShell)
.\install.ps1
```

If macOS/Linux blocks the script with `permission denied`, make it executable first, then rerun it:
```sh
chmod +x install.sh
./install.sh
```

If Windows blocks the script with an execution-policy error, run:
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

If `gcheck` isn't found right after installing, open a new terminal window
— the scripts may have just updated your `PATH`.

### Manual install

| Command | Isolated venv | Global `gcheck` command | Editable (code edits apply immediately) |
|---|---|---|---|
| `pipx install --editable .` (recommended) | Yes | Yes | Yes |
| `pipx install .` | Yes | Yes | No — rerun with `--force` after changes |
| `pip install -e .` | No, installs into active env | Yes, within that env | Yes |
| `pip install --require-hashes -r requirements.txt` | No, installs into active env | No — no entry point, run via `python -m gcheck` | N/A |

```sh
# recommended for active development
pipx install --editable .
```

`pip install --require-hashes -r requirements.txt` installs the exact pinned, hash-verified versions from the lock file but doesn't install `gcheck` itself — use it to reproduce a known-good dependency set, then still run `pip install -e . --no-deps` to get the `gcheck` command.

---

## Configuration

Optional — only needed for the API key connectivity check. Copy `.env.example` to `.env` in your working directory and add your key:

```
GEMINI_API_KEY=your_api_key_here
```

---

## Usage

```sh
gcheck              # Select language in TUI
gcheck --lang en    # English
gcheck --lang zh    # 中文
gcheck --lang es    # Español
gcheck --lang ja    # 日本語
```

---

## Uninstall

```sh
pipx uninstall gcheck
```

If `pipx: command not found` — `install.sh` may have installed `pipx` via `pip install --user` (no Homebrew), which only adds it to your PATH in *new* terminal windows. Either open a new terminal and retry, or run it through Python directly:

```sh
python3 -m pipx uninstall gcheck
```

If you installed with `pip install -e .` instead of `pipx`, use `pip uninstall gcheck` in the same environment you installed it into.

To also remove `pipx` itself: `pipx uninstall-all` (removes every pipx-managed app), then `pip uninstall pipx` or `brew uninstall pipx` depending on how `pipx` was installed.

---

## Testing

The test suite runs against a local checkout:

```sh
pip install -e ".[test]"
pytest unit_test
```

CI runs the same suite on every push and pull request across Ubuntu, macOS,
and Windows on Python 3.10 and 3.13 — see
[.github/workflows/unit-tests.yml](.github/workflows/unit-tests.yml). For what
is covered and what deliberately isn't, see
[unit_test/README.md](unit_test/README.md).

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the
full text.

