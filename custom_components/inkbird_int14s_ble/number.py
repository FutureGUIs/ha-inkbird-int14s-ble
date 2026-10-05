"""Experimental authenticated BLE food-high writes."""

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory

from .entity import InkbirdEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            *(InkbirdTarget(entry.runtime_data, probe) for probe in range(4)),
            InkbirdBrightness(entry.runtime_data),
        ]
    )


class InkbirdTarget(InkbirdEntity, RestoreNumber):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°F"
    _attr_native_min_value = 32
    _attr_native_max_value = 212
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, probe):
        super().__init__(
            coordinator,
            f"probe{probe + 1}_food_high",
            f"Probe {probe + 1} target",
        )
        self.probe = probe

    @property
    def native_value(self):
        return self.coordinator.targets[self.probe]

    @property
    def extra_state_attributes(self):
        return {
            "experimental": True,
            "value_source": self.coordinator.target_sources[self.probe],
            "write_status": self.coordinator.write_status[self.probe],
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        previous = await self.async_get_last_number_data()
        if (
            previous
            and previous.native_value is not None
            and self.coordinator.targets[self.probe] is None
        ):
            self.coordinator.targets[self.probe] = previous.native_value
            self.coordinator.target_sources[self.probe] = "restored_last_requested"

    async def async_set_native_value(self, value):
        await self.coordinator.write_food_high(self.probe, value)


class InkbirdBrightness(InkbirdEntity, RestoreNumber):
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:brightness-6"

    def __init__(self, coordinator):
        super().__init__(coordinator, "brightness", "Display brightness")

    @property
    def native_value(self):
        return self.coordinator.brightness

    @property
    def extra_state_attributes(self):
        return {
            "experimental": True,
            "write_status": self.coordinator.brightness_write_status,
        }

    async def async_set_native_value(self, value):
        await self.coordinator.write_brightness(value)
