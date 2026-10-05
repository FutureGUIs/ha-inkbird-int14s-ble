"""Station display configuration."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .entity import InkbirdEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([InkbirdTemperatureUnit(entry.runtime_data)])


class InkbirdTemperatureUnit(InkbirdEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:temperature-celsius"

    def __init__(self, coordinator):
        super().__init__(coordinator, "temperature_unit", "Temperature unit")
        self._attr_options = ["Celsius", "Fahrenheit"]

    @property
    def current_option(self):
        return {"C": "Celsius", "F": "Fahrenheit"}.get(
            self.coordinator.temperature_unit
        )

    @property
    def extra_state_attributes(self):
        return {"write_status": self.coordinator.unit_write_status}

    async def async_select_option(self, option):
        if option not in self.options:
            raise HomeAssistantError("Select Celsius or Fahrenheit")
        await self.coordinator.write_temperature_unit(
            "C" if option == "Celsius" else "F"
        )
