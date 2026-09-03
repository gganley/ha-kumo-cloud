"""Client for the Kumo Cloud V3 API.

Mitsubishi's cloud exposes each indoor unit at /v3/devices/{serial}: a GET
returns the full live state, and a PATCH of the same field names writes it.
That pair is the whole control surface this integration needs.

Note on why this exists at all: the units also speak a local HTTP API, which is
what the core `mitsubishi_comfort` integration uses. That API needs a per-device
password which the cloud used to hand out in Socket.IO `adapter_update` events.
As of 2026-09-03 the cloud no longer sends it (nor `cryptoSerial`), and it was
never persisted anywhere, so local control cannot be re-established. Cloud
control still works, hence this integration.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import APP_VERSION, BASE_URL, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_BASE_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "x-app-version": APP_VERSION,
}


class KumoCloudError(Exception):
    """A transport or server-side failure talking to the cloud.

    Also covers aiohttp's RuntimeError("Session is closed"), which a poll can
    hit if it races Home Assistant's shutdown; the coordinator should treat
    that as a normal retryable failure rather than a crash.
    """


class KumoCloudAuthError(KumoCloudError):
    """Credentials were rejected."""


class KumoCloudApi:
    """Minimal authenticated client for the Kumo Cloud V3 API."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {**_BASE_HEADERS, "Authorization": f"Bearer {self._access_token}"}

    async def async_login(self) -> None:
        """Authenticate and store the access/refresh token pair."""
        body = {
            "username": self._username,
            "password": self._password,
            "appVersion": APP_VERSION,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/v3/login",
                headers=_BASE_HEADERS,
                json=body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status in (401, 403):
                    raise KumoCloudAuthError(f"Login rejected: HTTP {resp.status}")
                if not resp.ok:
                    raise KumoCloudError(f"Login failed: HTTP {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
            raise KumoCloudError(f"Login error: {err}") from err

        token = data.get("token", {})
        self._access_token = token.get("access")
        self._refresh_token = token.get("refresh")
        if not self._access_token:
            raise KumoCloudAuthError("Login response contained no access token")

    async def _async_refresh_token(self) -> None:
        """Exchange the refresh token for a new access token."""
        if not self._refresh_token:
            raise KumoCloudAuthError("No refresh token held")

        headers = {**_BASE_HEADERS, "Authorization": f"Bearer {self._refresh_token}"}
        try:
            async with self._session.post(
                f"{BASE_URL}/v3/refresh",
                headers=headers,
                json={"refresh": self._refresh_token},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status in (401, 403):
                    raise KumoCloudAuthError(f"Refresh rejected: HTTP {resp.status}")
                if not resp.ok:
                    raise KumoCloudError(f"Refresh failed: HTTP {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
            raise KumoCloudError(f"Refresh error: {err}") from err

        self._access_token = data.get("access")
        self._refresh_token = data.get("refresh")
        if not self._access_token:
            raise KumoCloudAuthError("Refresh response contained no access token")

    async def _async_request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        """Make an authenticated request, refreshing the token once on a 401."""
        if self._access_token is None:
            await self.async_login()

        for attempt in (1, 2):
            try:
                async with self._session.request(
                    method,
                    f"{BASE_URL}{path}",
                    headers=self._auth_headers,
                    json=json,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        await self._async_refresh_token()
                        continue
                    if resp.status in (401, 403):
                        raise KumoCloudAuthError(
                            f"{method} {path} unauthorized: HTTP {resp.status}"
                        )
                    if not resp.ok:
                        raise KumoCloudError(f"{method} {path} failed: HTTP {resp.status}")
                    return await resp.json()
            except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
                raise KumoCloudError(f"{method} {path} error: {err}") from err

        raise KumoCloudError(f"{method} {path} failed after token refresh")

    async def async_get_account(self) -> dict[str, Any]:
        """Return the authenticated account, used as the config entry identity."""
        return await self._async_request("GET", "/v3/accounts/me")

    async def async_get_sites(self) -> list[dict[str, Any]]:
        """Return every site on the account."""
        result = await self._async_request("GET", "/v3/sites/")
        return result if isinstance(result, list) else []

    async def async_get_zones(self, site_id: str) -> list[dict[str, Any]]:
        """Return the zones of a site. Each carries an `adapter` with its serial."""
        result = await self._async_request("GET", f"/v3/sites/{site_id}/zones")
        return result if isinstance(result, list) else []

    async def async_get_device(self, serial: str) -> dict[str, Any]:
        """Return the live state of one indoor unit."""
        return await self._async_request("GET", f"/v3/devices/{serial}")

    async def async_get_device_status(self, serial: str) -> dict[str, Any]:
        """Return an indoor unit's adapter status.

        This is where the LAN MAC and the unit's setpoint limits live; the
        device object itself carries neither.
        """
        return await self._async_request("GET", f"/v3/devices/{serial}/status")

    async def async_patch_device(
        self, serial: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """Write state to one indoor unit and return the resulting device object."""
        _LOGGER.debug("PATCH device %s: %s", serial, changes)
        return await self._async_request("PATCH", f"/v3/devices/{serial}", json=changes)
