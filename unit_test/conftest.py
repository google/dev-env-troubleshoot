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


@pytest.fixture(autouse=True)
def _reset_i18n_state():
    """Keep gcheck.i18n's global _strings dict from leaking between tests.

    Without this, one test calling set_language("es") would leave later
    tests seeing Spanish strings instead of the raw key fallback (the
    default, un-loaded state), depending on test execution order.
    """
    i18n._strings = {}
    yield
    i18n._strings = {}
