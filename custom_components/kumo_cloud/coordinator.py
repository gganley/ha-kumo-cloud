"""Data update coordinator for Kumo Cloud."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KumoCloudApi, KumoCloudAuthError, KumoCloudError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KumoDevice:
    """The static identity of one indoor unit, learned once at setup."""

    serial: str
    name: str
    mac: str | None
    model: str | None


type KumoCloudConfigEntry = ConfigEntry[KumoCloudCoordinator]


class KumoCloudCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll every known indoor unit and keep its latest cloud state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KumoCloudConfigEntry,
        api: KumoCloudApi,
        devices: dict[str, KumoDevice],
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.devices = devices

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch the state of all units concurrently."""
        try:
            results = await asyncio.gather(
                *(self.api.async_get_device(serial) for serial in self.devices)
            )
        except KumoCloudAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KumoCloudError as err:
            raise UpdateFailed(str(err)) from err

        return dict(zip(self.devices, results, strict=True))

    def device_state(self, serial: str) -> dict[str, Any]:
        """Return the last known state of one unit."""
        return self.data.get(serial, {}) if self.data else {}

    async def async_patch(self, serial: str, changes: dict[str, Any]) -> None:
        """Write state to a unit and fold the response back into the cache."""
        try:
            updated = await self.api.async_patch_device(serial, changes)
        except KumoCloudAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        if isinstance(updated, dict) and self.data is not None:
            merged = dict(self.data)
            merged[serial] = updated
            self.async_set_updated_data(merged)
