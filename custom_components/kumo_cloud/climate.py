"""Climate platform for Kumo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CLOUD_TO_FAN_MODE,
    DOMAIN,
    FAN_MODE_TO_CLOUD,
    MAX_TEMP_C,
    MIN_TEMP_C,
    SWING_MODE_TO_CLOUD,
    SWING_OFF,
    SWING_ON,
)
from .coordinator import KumoCloudConfigEntry, KumoCloudCoordinator, KumoDevice

HVAC_MODE_TO_CLOUD = {
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "vent",
    HVACMode.HEAT_COOL: "auto",
}
CLOUD_TO_HVAC_MODE = {v: k for k, v in HVAC_MODE_TO_CLOUD.items()} | {
    "fan": HVACMode.FAN_ONLY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KumoCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one climate entity per indoor unit."""
    coordinator = entry.runtime_data
    async_add_entities(
        KumoCloudClimate(coordinator, device) for device in coordinator.devices.values()
    )


class KumoCloudClimate(CoordinatorEntity[KumoCloudCoordinator], ClimateEntity):
    """A Mitsubishi indoor unit, controlled through the Kumo cloud."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = MIN_TEMP_C
    _attr_max_temp = MAX_TEMP_C
    _attr_fan_modes = list(FAN_MODE_TO_CLOUD)
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.HEAT_COOL,
    ]

    def __init__(
        self, coordinator: KumoCloudCoordinator, device: KumoDevice
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = device.serial
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.serial)},
            name=device.name,
            manufacturer="Mitsubishi Electric",
            model=device.model,
            serial_number=device.serial,
            connections=(
                {(CONNECTION_NETWORK_MAC, device.mac)} if device.mac else set()
            ),
        )

    @property
    def _state(self) -> dict[str, Any]:
        """Return this unit's slice of the coordinator data."""
        return self.coordinator.device_state(self._device.serial)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the adapter's cloud link, which can drop on weak wifi.

        Deliberately *not* folded into `available`: the cloud keeps serving the
        unit's last-known state while its adapter is offline and still accepts
        writes (queueing them for reconnect), so marking the entity unavailable
        would make it flicker to "No Response" in Apple Home for no gain.
        """
        return {
            "cloud_connected": self._state.get("connected"),
            "wifi_rssi": self._state.get("rssi"),
            "fan_speed_locked": self.fan_speed_locked,
            # The unit's actual speed, including values we cannot set --
            # "quiet", and "auto" when it was chosen from the Comfort app.
            # `fan_mode` reads None for those, so surface the truth here.
            "cloud_fan_speed": self._state.get("fanSpeed"),
        }

    @property
    def fan_speed_locked(self) -> bool:
        """Return whether the unit is currently refusing fan-speed changes.

        In dry (dehumidify) mode the unit drives the fan itself to manage coil
        temperature and rejects any speed we send: the cloud PATCH is accepted
        but comes straight back with fanSpeed "auto".
        """
        return self._state.get("operationMode") == "dry"

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the features available in the current mode."""
        features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if self.hvac_mode is HVACMode.HEAT_COOL:
            return features | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self.hvac_mode is not HVACMode.FAN_ONLY:
            return features | ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current mode, or off when the unit is powered down."""
        if not self._state:
            return None
        if not self._state.get("power"):
            return HVACMode.OFF
        return CLOUD_TO_HVAC_MODE.get(self._state.get("operationMode", ""))

    @property
    def current_temperature(self) -> float | None:
        """Return the room temperature."""
        return self._state.get("roomTemp")

    @property
    def current_humidity(self) -> float | None:
        """Return the room humidity, for units that measure it."""
        return self._state.get("humidity")

    @property
    def target_temperature(self) -> float | None:
        """Return the setpoint for the current single-setpoint mode."""
        if self.hvac_mode is HVACMode.HEAT:
            return self._state.get("spHeat")
        if self.hvac_mode in (HVACMode.COOL, HVACMode.DRY):
            return self._state.get("spCool")
        return None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the cooling setpoint in auto mode."""
        return self._state.get("spCool")

    @property
    def target_temperature_low(self) -> float | None:
        """Return the heating setpoint in auto mode."""
        return self._state.get("spHeat")

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan speed under HomeKit-compatible names."""
        return CLOUD_TO_FAN_MODE.get(self._state.get("fanSpeed", ""))

    @property
    def swing_mode(self) -> str | None:
        """Return whether the vane is sweeping."""
        if not self._state:
            return None
        return SWING_ON if self._state.get("airDirection") == "swing" else SWING_OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the operating mode, powering the unit on or off as needed."""
        if hvac_mode is HVACMode.OFF:
            await self._async_command({"power": 0})
            return
        await self._async_command(
            {"power": 1, "operationMode": HVAC_MODE_TO_CLOUD[hvac_mode]}
        )

    async def async_turn_on(self) -> None:
        """Power the unit on, restoring the mode it was last in."""
        previous = self._state.get("previousOperationMode") or "cool"
        await self._async_command({"power": 1, "operationMode": previous})

    async def async_turn_off(self) -> None:
        """Power the unit off."""
        await self._async_command({"power": 0})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set one or both setpoints."""
        changes: dict[str, Any] = {}
        if (high := kwargs.get(ATTR_TARGET_TEMP_HIGH)) is not None:
            changes["spCool"] = high
        if (low := kwargs.get(ATTR_TARGET_TEMP_LOW)) is not None:
            changes["spHeat"] = low
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            if self.hvac_mode is HVACMode.HEAT:
                changes["spHeat"] = temp
            else:
                changes["spCool"] = temp
        if changes:
            await self._async_command(changes)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed.

        Deliberately not blocked when `fan_speed_locked` is true. That flag is
        derived from the cloud's `operationMode`, which lags reality by minutes,
        so refusing the call means rejecting a legitimate fan change made just
        after leaving dry mode -- the state we read is still stale. Send it and
        let the unit decide; `fan_speed_locked` is advisory only.
        """
        await self._async_command({"fanSpeed": FAN_MODE_TO_CLOUD[fan_mode]})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Start or stop the vane sweep."""
        await self._async_command({"airDirection": SWING_MODE_TO_CLOUD[swing_mode]})

    async def _async_command(self, changes: dict[str, Any]) -> None:
        """Send a command to the unit and refresh this entity."""
        await self.coordinator.async_send_command(self._device.serial, changes)
