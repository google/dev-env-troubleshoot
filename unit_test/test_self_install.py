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

import sys

import pytest

import gcheck.self_install as self_install


def test_self_install_not_frozen_prints_message_and_returns(capsys, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    self_install.self_install()
    out = capsys.readouterr().out
    assert "only applies to the standalone" in out


def test_self_install_frozen_dispatches_to_windows_installer(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(self_install.platform, "system", lambda: "Windows")
    called = []
    monkeypatch.setattr(self_install, "_install_windows", lambda: called.append("windows"))
    self_install.self_install()
    assert called == ["windows"]


def test_self_install_frozen_dispatches_to_macos_installer(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(self_install.platform, "system", lambda: "Darwin")
    called = []
    monkeypatch.setattr(self_install, "_install_macos", lambda: called.append("macos"))
    self_install.self_install()
    assert called == ["macos"]


def test_self_install_frozen_unsupported_platform_exits_with_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(self_install.platform, "system", lambda: "Linux")
    with pytest.raises(SystemExit) as exc_info:
        self_install.self_install()
    assert exc_info.value.code == 1
    assert "isn't supported on Linux" in capsys.readouterr().err


class FakeWinReg:
    """Minimal stand-in for the parts of `winreg` self_install.py uses."""

    REG_SZ = 1
    REG_EXPAND_SZ = 2
    HKEY_CURRENT_USER = object()
    KEY_READ = 0x1
    KEY_WRITE = 0x2

    def __init__(self, existing_path=None, existing_type=None):
        self.existing_path = existing_path
        self.existing_type = existing_type if existing_type is not None else self.REG_EXPAND_SZ
        self.set_calls = []
        self.closed = False

    def OpenKey(self, hkey, subkey, res, sam):
        return "fake-key-handle"

    def QueryValueEx(self, key, name):
        if self.existing_path is None:
            raise FileNotFoundError()
        return self.existing_path, self.existing_type

    def SetValueEx(self, key, name, reserved, value_type, value):
        self.set_calls.append((name, value_type, value))

    def CloseKey(self, key):
        self.closed = True


@pytest.fixture
def fake_ctypes(monkeypatch):
    import types

    fake = types.SimpleNamespace()
    fake.windll = types.SimpleNamespace(
        user32=types.SimpleNamespace(SendMessageTimeoutW=lambda *a, **kw: None)
    )
    fake.c_long = lambda: 0
    fake.byref = lambda x: x
    monkeypatch.setitem(sys.modules, "ctypes", fake)
    return fake


def test_add_to_path_windows_appends_when_not_present(monkeypatch, fake_ctypes, capsys):
    existing = ";".join([r"C:\Windows", r"C:\Windows\System32"])
    target_dir = r"C:\Users\me\AppData\Local\Programs\gcheck"
    fake_winreg = FakeWinReg(existing_path=existing)
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    self_install._add_to_user_path_windows(target_dir)

    assert fake_winreg.set_calls == [
        ("Path", fake_winreg.REG_EXPAND_SZ, existing + ";" + target_dir)
    ]
    assert "Added" in capsys.readouterr().out
    assert fake_winreg.closed is True


def test_add_to_path_windows_noop_when_already_present(monkeypatch, fake_ctypes, capsys):
    target_dir = r"C:\Users\me\AppData\Local\Programs\gcheck"
    fake_winreg = FakeWinReg(existing_path=";".join([r"C:\Windows", target_dir]))
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    self_install._add_to_user_path_windows(target_dir)

    assert fake_winreg.set_calls == []
    assert "Already on PATH" in capsys.readouterr().out


def test_add_to_path_windows_no_existing_path_creates_new_value(monkeypatch, fake_ctypes):
    fake_winreg = FakeWinReg(existing_path=None)
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    self_install._add_to_user_path_windows(r"C:\gcheck")

    assert fake_winreg.set_calls == [("Path", fake_winreg.REG_EXPAND_SZ, r"C:\gcheck")]
