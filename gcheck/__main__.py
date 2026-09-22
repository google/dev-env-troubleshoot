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

import os

import click
from dotenv import load_dotenv

load_dotenv()

from .app import GcheckApp


@click.group(invoke_without_command=True)
@click.option("--lang", "-l", default=None, help="Language: en, zh, es, or ja")
@click.pass_context
def main(ctx: click.Context, lang: str | None) -> None:
    if ctx.invoked_subcommand is None:
        GcheckApp(flag_lang=lang).run()
        # Background diagnostic/API checks run as thread-pool workers with
        # multi-second socket timeouts (up to 15s for the Gemini call).
        # CPython's ThreadPoolExecutor registers an atexit hook that blocks
        # process exit until every such thread finishes -- so without this,
        # quitting while a check is still in flight leaves the terminal
        # looking frozen (no new shell prompt) for however long that socket
        # call takes to time out, even though the TUI itself already closed
        # cleanly. os._exit skips that wait; the OS reclaims the sockets.
        os._exit(0)


@main.command()
def install() -> None:
    """Copy the standalone binary to a stable location and add it to PATH."""
    from .self_install import self_install

    self_install()


if __name__ == "__main__":
    main()
