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

from click.testing import CliRunner

from gcheck.__main__ import main


def test_install_subcommand_calls_self_install(mocker):
    spy = mocker.patch("gcheck.self_install.self_install")
    result = CliRunner().invoke(main, ["install"])
    assert result.exit_code == 0
    spy.assert_called_once()


def test_default_invocation_runs_app_and_force_exits(mocker):
    # main()'s no-subcommand path ends with a real os._exit(0), which would
    # kill this whole test process outright -- both GcheckApp (so .run()
    # never blocks on a real Textual event loop) and os._exit must be
    # mocked before invoking, not just have their effects asserted after.
    mock_app_cls = mocker.patch("gcheck.__main__.GcheckApp")
    mock_exit = mocker.patch("gcheck.__main__.os._exit")

    CliRunner().invoke(main, [])

    mock_app_cls.assert_called_once_with(flag_lang=None)
    mock_app_cls.return_value.run.assert_called_once()
    mock_exit.assert_called_once_with(0)


def test_lang_flag_is_passed_through_to_the_app(mocker):
    mock_app_cls = mocker.patch("gcheck.__main__.GcheckApp")
    mocker.patch("gcheck.__main__.os._exit")

    CliRunner().invoke(main, ["--lang", "es"])

    mock_app_cls.assert_called_once_with(flag_lang="es")


def test_short_lang_flag_alias(mocker):
    mock_app_cls = mocker.patch("gcheck.__main__.GcheckApp")
    mocker.patch("gcheck.__main__.os._exit")

    CliRunner().invoke(main, ["-l", "ja"])

    mock_app_cls.assert_called_once_with(flag_lang="ja")
