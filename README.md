# Kumo Cloud for Home Assistant

Cloud control for Mitsubishi mini-split indoor units (Kumo Cloud / Comfort app),
exposing each unit as a single Home Assistant `climate` entity.

## Why this exists

Home Assistant ships a core `mitsubishi_comfort` integration that talks to the
units over their **local** HTTP API. That API requires a per-device password
which the Kumo cloud used to deliver in Socket.IO `adapter_update` events.

As of **2026-09-03** the cloud no longer sends that field, nor `cryptoSerial`:

```
Socket.IO: found passwords for 0/5 devices
```

A full dump of the Socket.IO stream contains zero occurrences of
`password`/`crypto`/`secret`/`key`/`token`, `GET /v3/devices/{serial}/status` no
longer returns `cryptoSerial`, and the legacy `geo-c.kumocloud.com/login` body
(the one `pykumo` used) is now just user preferences. Because the core
integration re-fetches those credentials on *every* startup and never persists
them, it cannot authenticate after a restart and all its entities go
`unavailable`.

Cloud control still works, so this integration uses it instead.

## Control surface

Discovered by probing the V3 API:

| | |
|---|---|
| Read | `GET /v3/devices/{serial}` |
| Write | `PATCH /v3/devices/{serial}` |
| Auth | `POST /v3/login`, `POST /v3/refresh` |

Writable fields: `power`, `operationMode`, `spCool`, `spHeat`, `spAuto`,
`fanSpeed`, `airDirection`.

## Fan speeds and Apple Home

The units have five hardware speeds — `superQuiet`, `quiet`, `low`, `powerful`,
`superPowerful` — plus `auto`. Home Assistant's HomeKit bridge only builds a
multi-step fan slider from names in its own list:

```python
# homeassistant/components/homekit/type_thermostats.py
ORDERED_FAN_SPEEDS = [FAN_LOW, FAN_MIDDLE, FAN_MEDIUM, FAN_HIGH]
```

and intersects that with the entity's `fan_modes`. The core integration reports
raw camelCase names, so the intersection is just `["low"]` — a one-step slider,
which is why Apple Home could only ever send 0% or 100%.

This integration therefore maps four of the five speeds onto HomeKit's own
names, giving a real four-notch slider plus the native Auto toggle, all on the
**single** thermostat accessory:

| HA fan mode | Unit speed |
|---|---|
| `low` | `superQuiet` |
| `middle` | `low` |
| `medium` | `powerful` |
| `high` | `superPowerful` |
| `auto` | `auto` |

`quiet` is the dropped one — it sits between `superQuiet` and `low`, so losing
it costs the least range. Change `FAN_MODE_TO_CLOUD` in `const.py` to pick a
different four.

## Install

Copy `custom_components/kumo_cloud` into your HA `config/custom_components/`,
restart, then add **Kumo Cloud** from Settings → Devices & Services. Or run
`./deploy.sh --restart`.
