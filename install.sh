#!/bin/sh
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

# Installs gcheck on macOS (and Linux) via pipx.
#
# Works two ways:
#   1. Local clone:  ./install.sh
#      Installs editably from this checkout -- code edits apply immediately.
#   2. One-liner (once the repo is public):
#      curl -fsSL https://raw.githubusercontent.com/google/dev-env-troubleshoot/main/install.sh | sh
#      Installs straight from GitHub, no local clone needed.
#
# It tells the two apart by checking whether it can find pyproject.toml next
# to itself on disk -- piped scripts have no such file, since there's
# nothing on disk to resolve a path to.

set -eu

GCHECK_REPO_URL="https://github.com/google/dev-env-troubleshoot.git"
GCHECK_RAW_BASE_URL="https://raw.githubusercontent.com/google/dev-env-troubleshoot/main"

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || SCRIPT_DIR=""

# Prompts "$1 [Y/n] " and returns 0 for yes, 1 for no *or* no terminal to ask
# on. Piped installs (curl | sh) have the script itself on stdin, so a plain
# `read` would consume script text instead of a real answer -- fall back to
# /dev/tty when stdin isn't a terminal, and to "no" if neither is available
# (e.g. CI), matching the old non-interactive behavior.
prompt_yes() {
  reply=""
  if [ -n "${CI:-}" ]; then
    return 1
  fi
  if [ -t 0 ]; then
    printf '%s [Y/n] ' "$1"
    read -r reply || true
  elif [ -r /dev/tty ]; then
    printf '%s [Y/n] ' "$1" > /dev/tty
    read -r reply < /dev/tty || true
  else
    return 1
  fi
  case "$reply" in
    [nN]*) return 1 ;;
    *) return 0 ;;
  esac
}

# `command -v pipx` only proves *something* named pipx is reachable -- it
# can succeed for a broken symlink, a stale interpreter shebang, or (as seen
# in practice) a leftover shell alias/function shadowing the real binary,
# none of which actually work. Confirm it behaves like pipx before trusting
# it anywhere in this script.
pipx_actually_works() {
  hash -r 2>/dev/null || true
  command -v pipx >/dev/null 2>&1 && pipx --version >/dev/null 2>&1
}

# If pipx resolves to something other than a real file on disk, it's a shell
# alias or function -- reinstalling pipx won't fix that, since the shadow
# will just mask the new install too once a new terminal picks it up. Warn
# so the user knows to look at their own shell config instead of assuming
# this script is broken.
warn_if_pipx_shadowed() {
  resolved="$(command -v pipx 2>/dev/null || true)"
  case "$resolved" in
    "" | /*) ;; # not found, or a real path -- nothing to warn about
    *)
      echo "warning: 'pipx' resolves to '$resolved', which looks like a shell alias or function, not a program." >&2
      echo "Run 'type pipx' and check your shell rc files (~/.zshrc, ~/.bashrc, etc.) for a conflicting definition." >&2
      ;;
  esac
}

# After installing pipx via an OS package manager, confirm it's actually
# resolvable in *this* shell before using it. PATH stripped by `sudo`'s
# secure_path, or a non-standard install prefix, can leave pipx installed but
# not yet callable here. If a plain PATH lookup fails, check the common
# install locations ourselves and prepend the first hit to PATH so the rest
# of *this script* can keep going -- this can't fix the PATH of the terminal
# that invoked us (that still needs a new terminal, see the closing message),
# but it avoids failing here with a confusing low-level "exec: pipx: not
# found" error further down.
require_pipx_on_path() {
  if pipx_actually_works; then
    return 0
  fi
  warn_if_pipx_shadowed

  for dir in /usr/local/bin /usr/bin /snap/bin "$HOME/.local/bin" \
             /home/linuxbrew/.linuxbrew/bin /opt/homebrew/bin; do
    if [ -x "$dir/pipx" ] && "$dir/pipx" --version >/dev/null 2>&1; then
      PATH="$dir:$PATH"
      export PATH
      hash -r 2>/dev/null || true
      return 0
    fi
  done

  if command -v brew >/dev/null 2>&1; then
    brew_bin="$(brew --prefix)/bin"
    if [ -x "$brew_bin/pipx" ] && "$brew_bin/pipx" --version >/dev/null 2>&1; then
      PATH="$brew_bin:$PATH"
      export PATH
      hash -r 2>/dev/null || true
      return 0
    fi
  fi

  echo "error: pipx was installed but is not working in this shell." >&2
  echo "Open a new terminal (so it picks up the updated PATH) and re-run this script." >&2
  exit 1
}

# Prints the path to pipx-requirements.txt (the hash-locked bootstrap deps
# for `pip install --require-hashes`), downloading it to a temp file first
# when run as a piped one-liner, since then there's no local checkout to
# find it next to. Caller is responsible for cleaning up the temp copy.
resolve_pipx_requirements() {
  reqs_candidate="$SCRIPT_DIR/pipx-requirements.txt"
  if [ -n "$SCRIPT_DIR" ] && [ -f "$reqs_candidate" ]; then
    echo "$reqs_candidate"
    return 0
  fi

  tmp_reqs="$(mktemp)" || { echo "error: mktemp failed." >&2; exit 1; }
  if ! curl -fsSL "$GCHECK_RAW_BASE_URL/pipx-requirements.txt" -o "$tmp_reqs"; then
    echo "error: couldn't download pipx-requirements.txt." >&2
    rm -f "$tmp_reqs"
    exit 1
  fi
  echo "$tmp_reqs"
}

# Tries to resolve a working `python3` after an install attempt. Checks
# PATH first, then common install locations directly, since a
# package-manager install can land somewhere `command -v` doesn't see yet
# in this same shell/process. Sets $PYTHON and succeeds only if it
# satisfies 3.10+.
verify_python() {
  hash -r 2>/dev/null || true
  for candidate in "$(command -v python3 2>/dev/null || true)" \
                   /usr/bin/python3 /usr/local/bin/python3 \
                   /opt/homebrew/bin/python3 \
                   /home/linuxbrew/.linuxbrew/bin/python3; do
    if [ -n "$candidate" ] && [ -x "$candidate" ] \
       && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$candidate"
      return 0
    fi
  done
  return 1
}

echo "==> Checking for Python 3.10+"

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "error: Python 3.10+ not found." >&2
  if command -v brew >/dev/null 2>&1; then
    if prompt_yes "Install it now with 'brew install python3'?"; then
      echo "==> Installing Python via Homebrew"
      if ! brew install python3 || ! verify_python; then
        echo "error: 'brew install python3' failed, or the installed Python still doesn't satisfy 3.10+." >&2
        exit 1
      fi
    else
      echo "Install it with: brew install python3" >&2
      exit 1
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    if prompt_yes "Install it now with 'sudo apt-get install -y python3'?"; then
      echo "==> Installing Python via apt"
      if ! sudo apt-get install -y python3 || ! verify_python; then
        echo "error: 'apt-get install python3' failed, or the installed Python still doesn't satisfy 3.10+." >&2
        exit 1
      fi
    else
      echo "Install it with: sudo apt-get install -y python3" >&2
      exit 1
    fi
  elif command -v dnf >/dev/null 2>&1; then
    if prompt_yes "Install it now with 'sudo dnf install -y python3'?"; then
      echo "==> Installing Python via dnf"
      if ! sudo dnf install -y python3 || ! verify_python; then
        echo "error: 'dnf install python3' failed, or the installed Python still doesn't satisfy 3.10+." >&2
        exit 1
      fi
    else
      echo "Install it with: sudo dnf install -y python3" >&2
      exit 1
    fi
  elif command -v pacman >/dev/null 2>&1; then
    if prompt_yes "Install it now with 'sudo pacman -S --noconfirm python'?"; then
      echo "==> Installing Python via pacman"
      if ! sudo pacman -S --noconfirm python || ! verify_python; then
        echo "error: 'pacman -S python' failed, or the installed Python still doesn't satisfy 3.10+." >&2
        exit 1
      fi
    else
      echo "Install it with: sudo pacman -S python" >&2
      exit 1
    fi
  else
    echo "Install it from https://www.python.org/downloads/ , then rerun this script." >&2
    exit 1
  fi
fi

echo "==> Using $("$PYTHON" --version) ($PYTHON)"

echo "==> Checking for pipx"

# PIPX_CMD is how we invoke pipx for the rest of this script. It's set
# per-install-method below because a freshly-installed pipx isn't always on
# PATH yet within this same running script (ensurepath only updates *future*
# shells' rc files), so a bare `pipx` right after installing it can fail
# with "command not found" even though the install itself succeeded.
PIPX_CMD="pipx"

if pipx_actually_works; then
  PIPX_CMD="pipx"
else
  warn_if_pipx_shadowed
  echo "==> pipx not found, installing it"

  # Prefer pip --user: it writes to the user's home directory, so it can't
  # hit the Homebrew Cellar permission errors that show up on some Macs
  # (usually Intel Macs where /usr/local ended up owned by another user).
  # Some Homebrew Pythons mark themselves "externally managed" (PEP 668) and
  # reject plain --user installs, so retry once with --break-system-packages
  # before giving up on pip entirely.
  #
  # --require-hashes pins pipx (and its own dependencies) to the exact,
  # known-good artifacts recorded in pipx-requirements.txt, so a compromised
  # or typosquatted PyPI upload can't slip in here unnoticed.
  pipx_reqs="$(resolve_pipx_requirements)"
  pip_install_ok=1
  if "$PYTHON" -m pip install --user --require-hashes -r "$pipx_reqs" \
    || "$PYTHON" -m pip install --user --break-system-packages --require-hashes -r "$pipx_reqs"; then
    pip_install_ok=0
  fi
  [ "$pipx_reqs" = "$SCRIPT_DIR/pipx-requirements.txt" ] || rm -f "$pipx_reqs"
  if [ "$pip_install_ok" -eq 0 ]; then
    "$PYTHON" -m pipx ensurepath
    # Installed as a module of $PYTHON just now -- invoke it the same way
    # rather than relying on the console-script being on PATH already.
    PIPX_CMD="$PYTHON -m pipx"
  elif command -v brew >/dev/null 2>&1; then
    echo "==> pip install failed, falling back to Homebrew"
    if ! brew install pipx; then
      echo >&2
      echo "error: Homebrew failed to install pipx." >&2
      echo "This is usually a Homebrew directory ownership issue. Try:" >&2
      echo "  sudo chown -R \"\$(whoami)\":admin \"\$(brew --prefix)\"/*" >&2
      echo "then run 'brew doctor' and re-run this script." >&2
      exit 1
    fi
    require_pipx_on_path
    pipx ensurepath
    PIPX_CMD="pipx"
  elif command -v apt-get >/dev/null 2>&1; then
    echo "==> pip install failed, falling back to apt"
    if prompt_yes "Install pipx now with 'sudo apt-get install -y pipx'?"; then
      if ! sudo apt-get install -y pipx; then
        echo "error: 'apt-get install pipx' failed." >&2
        echo "Install it manually: https://pipx.pypa.io/stable/installation/" >&2
        exit 1
      fi
      require_pipx_on_path
      pipx ensurepath
      PIPX_CMD="pipx"
    else
      echo "Install it with: sudo apt-get install -y pipx" >&2
      exit 1
    fi
  elif command -v dnf >/dev/null 2>&1; then
    echo "==> pip install failed, falling back to dnf"
    if prompt_yes "Install pipx now with 'sudo dnf install -y pipx'?"; then
      if ! sudo dnf install -y pipx; then
        echo "error: 'dnf install pipx' failed." >&2
        echo "Install it manually: https://pipx.pypa.io/stable/installation/" >&2
        exit 1
      fi
      require_pipx_on_path
      pipx ensurepath
      PIPX_CMD="pipx"
    else
      echo "Install it with: sudo dnf install -y pipx" >&2
      exit 1
    fi
  elif command -v pacman >/dev/null 2>&1; then
    echo "==> pip install failed, falling back to pacman"
    if prompt_yes "Install pipx now with 'sudo pacman -S --noconfirm python-pipx'?"; then
      if ! sudo pacman -S --noconfirm python-pipx; then
        echo "error: 'pacman -S python-pipx' failed." >&2
        echo "Install it manually: https://pipx.pypa.io/stable/installation/" >&2
        exit 1
      fi
      require_pipx_on_path
      pipx ensurepath
      PIPX_CMD="pipx"
    else
      echo "Install it with: sudo pacman -S python-pipx" >&2
      exit 1
    fi
  else
    echo "error: could not install pipx (pip failed and no supported package manager was found)." >&2
    echo "Install it manually: https://pipx.pypa.io/stable/installation/" >&2
    exit 1
  fi
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
  echo "==> Installing gcheck (editable) from local checkout: $SCRIPT_DIR"
  # A pre-existing pipx defaults to the uv backend when uv is on PATH, and
  # rejects an uv that's older than it requires (e.g. "pipx needs
  # uv>=0.9.17, but ... reports 0.8.2"). Rather than parse that message,
  # just retry once with the pip backend, which pipx always supports.
  if ! $PIPX_CMD install --force --editable "$SCRIPT_DIR"; then
    # A venv from an earlier attempt records its backend at creation time,
    # so --force alone won't flip it -- uninstall first (ignore failure if
    # it never existed) so the retry actually creates a fresh pip-backed venv.
    echo "==> pipx install failed, retrying with --backend pip (uv may be missing or outdated)"
    $PIPX_CMD uninstall gcheck >/dev/null 2>&1 || true
    $PIPX_CMD install --force --editable "$SCRIPT_DIR" --backend pip
  fi
else
  echo "==> Checking for git"
  if ! command -v git >/dev/null 2>&1; then
    echo "error: git not found -- required to install gcheck from GitHub." >&2
    if command -v brew >/dev/null 2>&1; then
      echo "Install it with: brew install git" >&2
    else
      echo "Install it from https://git-scm.com/downloads , then rerun this script." >&2
    fi
    exit 1
  fi
  echo "==> Installing gcheck from $GCHECK_REPO_URL"
  if ! $PIPX_CMD install --force "git+$GCHECK_REPO_URL"; then
    echo "==> pipx install failed, retrying with --backend pip (uv may be missing or outdated)"
    $PIPX_CMD uninstall gcheck >/dev/null 2>&1 || true
    $PIPX_CMD install --force "git+$GCHECK_REPO_URL" --backend pip
  fi
fi

echo
echo "Done. Run 'gcheck' to start."
echo "If 'gcheck' isn't found, open a new terminal window (pipx just updated your PATH)."
