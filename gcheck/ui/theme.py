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

from textual.theme import Theme

WHITE = "#E8EAED"
BLUE = "#8AB4F8"
YELLOW = "#FDD663"
RED = "#F28B82"
GREEN = "#87FFC5"
PURPLE = "#F4B5FB"

PRIMARY_BUTTON = WHITE #filled
SECONDARY_BUTTON = WHITE #outline and text
THERTIARY_BUTTON = "#3C4043"

TITLE = "#8AB4F8"
BACKGROUND = "#202124"


SUCCESS_EMOJI = "🥳"
DIAGNOSTIC_EMOJI = "🔎"
RECOMMENDATION_EMOJI = "🍀"
ERROR_EMOJI = "❌"

GCHECK_DARK_THEME = Theme(
    name="gcheck-dark",
    primary=BLUE,
    accent=YELLOW,
    error=RED,
    success=GREEN,
    foreground=WHITE,
    background=BACKGROUND,
    surface=BACKGROUND,
    panel=BACKGROUND,
    dark=True,
    # Exposed as $purple/$title in app.tcss: $purple marks the API key input
    # field (the one widget holding a secret), $title is used for every
    # screen/section heading so it's decoupled from $primary (which now also
    # doubles as the recommendation-zone text color).
    variables={
        "purple": PURPLE,
        "title": TITLE,
        "button-primary": PRIMARY_BUTTON,
        "button-secondary": SECONDARY_BUTTON,
        "button-tertiary": THERTIARY_BUTTON,
    },
)

