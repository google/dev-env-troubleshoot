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

import socket

import gcheck.gate as gate


def test_check_gate_true_when_connection_succeeds(mocker):
    fake_conn = mocker.MagicMock()
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False
    mocker.patch("gcheck.gate.socket.create_connection", return_value=fake_conn)
    assert gate.check_gate() is True


def test_check_gate_false_on_os_error(mocker):
    mocker.patch("gcheck.gate.socket.create_connection", side_effect=OSError("refused"))
    assert gate.check_gate() is False


def test_check_gate_false_on_timeout(mocker):
    mocker.patch("gcheck.gate.socket.create_connection", side_effect=socket.timeout())
    assert gate.check_gate() is False


def test_check_gate_uses_expected_host_port_and_timeout(mocker):
    spy = mocker.patch("gcheck.gate.socket.create_connection", side_effect=OSError())
    gate.check_gate()
    spy.assert_called_once_with((gate.HOST, gate.PORT), timeout=gate.TIMEOUT)
