"""Switch platform for Kumo Cloud.

HomeKit's Thermostat service only has Off/Heat/Cool/Auto, so dry (dehumidify)
mode cannot be reached from Apple Home through the climate entity at all --
Home Assistant's bridge deliberately drops HVACMode.DRY when COOL is also
available (homekit/type_thermostats.py: "Prefer ... COOL over FAN_ONLY, DRY").

A plain switch is the way to give Apple Home and Siri a handle on it.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KumoCloudConfigEntry, KumoCloudCoordinator, KumoDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KumoCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a dry-mode switch per indoor unit."""
    coordinator = entry.runtime_data
    async_add_entities(
        KumoDryModeSwitch(coordinator, device)
        for device in coordinator.devices.values()
    )


class KumoDryModeSwitch(CoordinatorEntity[KumoCloudCoordinator], SwitchEntity):
    """Turns dehumidify mode on and off for one indoor unit."""

    _attr_has_entity_name = True
    _attr_name = "Dry mode"
    _attr_icon = "mdi:water-percent"

    def __init__(
        self, coordinator: KumoCloudCoordinator, device: KumoDevice
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.serial}_dry_mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device.serial)})

    @property
    def _state(self) -> dict[str, Any]:
        return self.coordinator.device_state(self._device.serial)

    @property
    def is_on(self) -> bool:
        """Return whether the unit is running in dry mode."""
        return bool(self._state.get("power")) and (
            self._state.get("operationMode") == "dry"
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the unit into dry mode."""
        await self.coordinator.async_send_command(
            self._device.serial, {"power": 1, "operationMode": "dry"}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Leave dry mode, returning to whatever the unit was doing before.

        `previousOperationMode` is the unit's own record of the mode it held
        before the current one, so switching dry off lands back where the user
        was rather than on an arbitrary default.
        """
        previous = self._state.get("previousOperationMode")
        if previous in (None, "", "dry"):
            previous = "cool"
        await self.coordinator.async_send_command(
            self._device.serial, {"power": 1, "operationMode": previous}
        )
