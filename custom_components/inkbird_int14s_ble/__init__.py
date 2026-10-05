"""The Inkbird INT-14S-BW integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant

from .coordinator import InkbirdCoordinator
from .registry import (
    async_link_station_entities,
    async_remove_legacy_target_text,
    async_update_station_firmware,
    async_watch_station_entities,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
]

type InkbirdConfigEntry = ConfigEntry[InkbirdCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: InkbirdConfigEntry) -> bool:
    """Set up Inkbird INT-14S-BW from a config entry."""
    address: str = entry.data[CONF_ADDRESS].upper()

    coordinator = InkbirdCoordinator(hass, address)
    entry.runtime_data = coordinator
    async_remove_legacy_target_text(hass, entry)
    entry.async_on_unload(async_watch_station_entities(hass, entry))

    # Register entities even while Bluetooth is unavailable. The background
    # connection owns retries; discovery and authentication must not hide entities.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_link_station_entities(hass, entry)
    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: async_update_station_firmware(hass, entry)
        )
    )
    await coordinator.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Stop the connection loop promptly on HA shutdown so it doesn't delay it.
    async def _on_stop(_event: Event) -> None:
        await coordinator.async_stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)
    )
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: InkbirdConfigEntry
) -> None:
    """Reload the entry when options (e.g. temperature unit) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: InkbirdConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok
