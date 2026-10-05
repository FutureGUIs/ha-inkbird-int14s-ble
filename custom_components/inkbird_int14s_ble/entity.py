"""Shared Bluetooth device identity and updates."""

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL


def station_device_info(address):
    return DeviceInfo(
        identifiers={(DOMAIN, address)},
        connections={(CONNECTION_BLUETOOTH, address)},
        manufacturer=MANUFACTURER,
        model=MODEL,
        name="INKBIRD INT-14S Bluetooth",
    )


class InkbirdEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_name = name
        self._attr_device_info = station_device_info(coordinator.address)

    @property
    def available(self):
        return self.coordinator.available

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
