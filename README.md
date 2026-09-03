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
| Auth | `POST /v3/login`, `POST /v3/refresh` |
| Read | `GET /v3/devices/{serial}` |
| Read (MAC, setpoint limits) | `GET /v3/devices/{serial}/status` |
| **Write** | **`POST /v3/devices/send-command`** |

Write body, sending only what changes:

```json
{"deviceSerial": "<serial>", "commands": {"fanSpeed": "quiet"}}
```

Command keys: `power`, `operationMode`, `spCool`, `spHeat`, `spAuto`,
`fanSpeed`, `airDirection`. The **`app-env: prd`** header is required alongside
`Authorization: Bearer` and `x-app-version`. The response is only
`{"devices":[serial]}` — no state — so re-read afterwards. Commands land in
about 4 seconds.

### Dead ends, documented so nobody repeats them

`PATCH /v3/devices/{serial}` (and `/v3/zones/{id}`) return HTTP 200, bump only
`updatedAt`, and **silently ignore the request body** — verified with six
payload shapes at 1-second polling resolution. No `/commands` sub-resource
exists anywhere under `/v3/{devices,zones,adapters,sites}`. Socket.IO is for
*receiving* push updates only; it does not accept commands.

Beware validating a write with a **no-op** (writing a field back to its own
value): a 200 plus an unchanged read is indistinguishable from an ignored
write. Always write a *changed* value and re-read.

Credit: the `send-command` endpoint is documented in
[ventz/kumo-cloud-v3-api-comfort-client](https://github.com/ventz/kumo-cloud-v3-api-comfort-client).

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

## Dry mode

In dry (dehumidify) mode the unit drives the fan itself and ignores any speed
you set -- the Comfort app cannot change it either, so this is the hardware's
behaviour, not an API limit. The cloud's reported `fanSpeed` is also sticky in
this mode: a write is accepted but the value that comes back is the one the
adapter last reported, which can lag by minutes.

The climate entity exposes `fan_speed_locked` as an advisory attribute. It does
*not* refuse the call: the flag derives from the cloud's `operationMode`, which
lags by minutes, so blocking would reject a legitimate fan change made right
after leaving dry mode.

HomeKit's Thermostat service has only Off/Heat/Cool/Auto, and Home Assistant's
bridge drops `HVACMode.DRY` whenever `COOL` is also offered, so dry is
unreachable from Apple Home through the thermostat. Each unit therefore also
gets a **Dry mode** switch, which Apple Home and Siri can see. Turning it off
returns the unit to its `previousOperationMode`.

## Why not local control?

The units also expose a local HTTP API (`PUT http://<ip>/api?m=<token>`) that
does reads and writes with no cloud involved, which would be strictly better.
Its token is `SHA256(W_PARAM ‖ SHA256(password ‖ body) ‖ 0x0840 ‖ … ‖
cryptoSerial bytes)` — no nonce, so tokens are stable per body.

It needs a per-device `password` and `cryptoSerial`, and the V3 cloud returns
both as **empty strings**. This is not specific to this integration: the
current `pykumo` (0.5.3) reports `found passwords for 0/5 devices` against the
same account, and it is tracked upstream as
[pykumo#78](https://github.com/dlarrick/pykumo/issues/78) (open since
2026-07-31) with no known workaround. The units themselves still answer on the
local API — they just reject unauthenticated requests — so if the credentials
ever become obtainable again, a local path is worth adding.
