"""The Kumo Cloud integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KumoCloudApi, KumoCloudAuthError, KumoCloudError
from .coordinator import KumoCloudConfigEntry, KumoCloudCoordinator, KumoDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]


async def async_setup_entry(
    hass: HomeAssistant, entry: KumoCloudConfigEntry
) -> bool:
    """Set up Kumo Cloud from a config entry."""
    api = KumoCloudApi(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    try:
        await api.async_login()
        devices = await _async_discover(api)
    except KumoCloudAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except KumoCloudError as err:
        raise ConfigEntryNotReady(str(err)) from err

    if not devices:
        raise ConfigEntryNotReady("No indoor units found on this account")

    coordinator = KumoCloudCoordinator(hass, entry, api, devices)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: KumoCloudConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_discover(api: KumoCloudApi) -> dict[str, KumoDevice]:
    """Walk the account's sites and zones to find every indoor unit.

    The zone carries the user's own room name, which is what we want the HA
    device to be called; the adapter carries the serial we address it by.
    """
    devices: dict[str, KumoDevice] = {}

    for site in await api.async_get_sites():
        site_id = site.get("id")
        if not site_id:
            continue
        for zone in await api.async_get_zones(site_id):
            adapter = zone.get("adapter") or {}
            serial = adapter.get("deviceSerial")
            if not serial or adapter.get("isHeadless"):
                continue

            # The zone payload carries neither the MAC nor the model. The
            # model is on the device object; the MAC is only on its /status.
            mac = None
            model = None
            try:
                detail = await api.async_get_device(serial)
            except KumoCloudError:
                _LOGGER.debug("Could not read device object for %s", serial)
            else:
                model = (detail.get("model") or {}).get("basicMaterial")
            try:
                status = await api.async_get_device_status(serial)
            except KumoCloudError:
                _LOGGER.debug("Could not read status for %s", serial)
            else:
                mac = status.get("mac")

            devices[serial] = KumoDevice(
                serial=serial,
                name=zone.get("name") or serial,
                mac=mac,
                model=model,
            )

    return devices
