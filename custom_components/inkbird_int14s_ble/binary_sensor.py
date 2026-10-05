"""Reported probe and base charging states."""

from time import time

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .entity import InkbirdEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [InkbirdCharging(coordinator, probe) for probe in range(4)]
        + [InkbirdCharging(coordinator, None)]
    )


class InkbirdCharging(InkbirdEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, probe):
        self._probe = probe
        key = "base_charging" if probe is None else f"probe{probe + 1}_charging"
        name = "Station charging" if probe is None else f"Probe {probe + 1} charging"
        super().__init__(coordinator, key, name)

    @property
    def is_on(self):
        timestamp = (
            self.coordinator._base_state_time
            if self._probe is None
            else self.coordinator._probe_state_times[self._probe]
        )
        if not timestamp or time() - timestamp > 90:
            return None
        if self._probe is None:
            return self.coordinator.base_charging
        return self.coordinator.probe_charging[self._probe]
