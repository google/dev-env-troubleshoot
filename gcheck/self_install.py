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

"""Self-install for the standalone PyInstaller binary: `gcheck install`.

Copies the running binary to a stable location and adds that location to
PATH, so `gcheck` works from any new terminal afterward. Only meaningful
for the frozen .exe/binary -- a pip/pipx install already has an entry
point on PATH via its own mechanism.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def self_install() -> None:
    if not getattr(sys, "frozen", False):
        print(
            "`gcheck install` only applies to the standalone .exe/binary "
            "build. A pip/pipx install already puts 'gcheck' on PATH."
        )
        return

    system = platform.system()
    if system == "Windows":
        _install_windows()
    elif system == "Darwin":
        _install_macos()
    else:
        print(f"error: self-install isn't supported on {system}.", file=sys.stderr)
        sys.exit(1)


def _install_windows() -> None:
    target_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "gcheck"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_exe = target_dir / "gcheck.exe"

    current_exe = Path(sys.executable).resolve()

    if current_exe != target_exe.resolve():
        shutil.copy2(current_exe, target_exe)
        print(f"Copied to {target_exe}")
    else:
        print(f"Already running from {target_exe}")

    _add_to_user_path_windows(str(target_dir))

    print("Open a new terminal window, then run 'gcheck' from anywhere.")


def _add_to_user_path_windows(directory: str) -> None:
    import ctypes
    import winreg

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
    )
    try:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            # No user PATH yet. REG_EXPAND_SZ is what Windows itself uses here.
            current, value_type = "", winreg.REG_EXPAND_SZ

        # Always ';' here: this is the Windows registry PATH value, which is
        # semicolon-delimited regardless of the OS this code runs on (e.g.
        # tests running on a Linux CI runner, where os.pathsep is ':').
        parts = [p for p in current.split(";") if p]
        if directory in parts:
            print("Already on PATH.")
            return

        new_value = ";".join(parts + [directory]) if current else directory
        # Preserve the existing value type (usually REG_EXPAND_SZ): forcing
        # REG_EXPAND_SZ onto a plain REG_SZ Path would make any literal
        # %VARS% already in it start expanding.
        winreg.SetValueEx(key, "Path", 0, value_type, new_value)
        print(f"Added {directory} to your user PATH.")
    finally:
        winreg.CloseKey(key)

    # Broadcast the change so some already-open apps (e.g. Explorer) notice
    # without a reboot. Open terminals still need to be restarted, since a
    # shell reads its environment once at startup.
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x1A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_long()
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        ctypes.byref(result),
    )


def _install_macos() -> None:
    target = Path("/usr/local/bin/gcheck")
    current_exe = Path(sys.executable).resolve()

    if current_exe == target.resolve():
        print(f"Already running from {target}")
        print("/usr/local/bin is on PATH by default -- run 'gcheck' from any terminal.")
        return

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_exe, target)
        target.chmod(0o755)
    except PermissionError:
        print(f"Need admin rights to write to {target.parent} -- you may be prompted for your password.")
        subprocess.run(["sudo", "mkdir", "-p", str(target.parent)], check=True)
        subprocess.run(["sudo", "cp", str(current_exe), str(target)], check=True)
        subprocess.run(["sudo", "chmod", "755", str(target)], check=True)

    print(f"Installed to {target}")
    print("/usr/local/bin is on PATH by default -- run 'gcheck' from any terminal.")
