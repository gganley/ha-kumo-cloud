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
# So we expose four of the five speeds under HomeKit's own names to get a real
# four-notch slider. "quiet" is the one dropped: it sits between superQuiet and
# low, so losing it costs the least range.
#
# "auto" is deliberately NOT offered. With the `heater_cooler` accessory type,
# HomeKit's HeaterCooler service has no auto-fan characteristic, so the moment
# an entity advertises an auto fan mode Home Assistant moves the whole fan onto
# a separate linked Fanv2 service -- which costs the single-tile layout that is
# the entire point of heater_cooler. See type_heater_coolers.py:
#
#     # The HeaterCooler service has no auto fan control, so when the entity
#     # exposes an auto fan mode ... the fan is exposed through a full linked
#     # fan service instead
#
# Auto is therefore set from the Comfort app, and reported (never set) here.
FAN_MODE_TO_CLOUD = {
    "low": "superQuiet",
    "middle": "low",
    "medium": "powerful",
    "high": "superPowerful",
}

# Reverse map for display. "quiet" and "auto" are not settable from HA, but the
# Comfort app and the unit's own schedules can select them, so they still have
# to read back as something. "auto" has no HA equivalent in the list above, so
# it reports as None and the raw value is surfaced via the `cloud_fan_speed`
# attribute instead.
CLOUD_TO_FAN_MODE = {
    "superQuiet": "low",
    "quiet": "low",
    "low": "middle",
    "powerful": "medium",
    "superPowerful": "high",
}

# Vane / swing. The unit exposes discrete vane positions plus a sweep; HomeKit
# only understands an on/off swing toggle, so that is what we present.
SWING_ON = "on"
SWING_OFF = "off"
SWING_MODE_TO_CLOUD = {SWING_ON: "swing", SWING_OFF: "auto"}
