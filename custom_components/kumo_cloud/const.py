"""Constants for the Kumo Cloud integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "kumo_cloud"

BASE_URL = "https://app-prod.kumocloud.com"
APP_VERSION = "3.2.4"

UPDATE_INTERVAL = timedelta(seconds=30)
REQUEST_TIMEOUT = 30

# Mitsubishi reports Celsius regardless of the app's display preference.
MIN_TEMP_C = 16.0
MAX_TEMP_C = 31.0

# Fan speeds.
#
# The unit has five hardware speeds plus auto:
#   superQuiet < quiet < low < powerful < superPowerful
#
# Home Assistant's HomeKit bridge only builds a multi-step fan slider from names
# in its own ORDERED_FAN_SPEEDS list -- see
# homeassistant/components/homekit/type_thermostats.py:
#
#     ORDERED_FAN_SPEEDS = [FAN_LOW, FAN_MIDDLE, FAN_MEDIUM, FAN_HIGH]
#
# and it takes the intersection with the entity's fan_modes. The core
# mitsubishi_comfort integration reports the raw camelCase names, which
# intersect that list only at "low" -- a one-step slider, which is why Apple
# Home could only ever send 0% or 100%.
#
# So we deliberately expose four of the five speeds under HomeKit's own names to
# get a real four-notch slider, and include "auto" so the bridge also adds the
# native Auto/Manual toggle. "quiet" is the one dropped: it sits between
# superQuiet and low, so losing it costs the least range.
FAN_MODE_TO_CLOUD = {
    "low": "superQuiet",
    "middle": "low",
    "medium": "powerful",
    "high": "superPowerful",
    "auto": "auto",
}

# Reverse map. "quiet" is not settable from HA but the Comfort app and the
# unit's own schedules can select it, so it still has to display as something.
CLOUD_TO_FAN_MODE = {
    "superQuiet": "low",
    "quiet": "low",
    "low": "middle",
    "powerful": "medium",
    "superPowerful": "high",
    "auto": "auto",
}

# Vane / swing. The unit exposes discrete vane positions plus a sweep; HomeKit
# only understands an on/off swing toggle, so that is what we present.
SWING_ON = "on"
SWING_OFF = "off"
SWING_MODE_TO_CLOUD = {SWING_ON: "swing", SWING_OFF: "auto"}
