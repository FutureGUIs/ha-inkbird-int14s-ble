"""Clear food targets and acknowledge temperature alarms over Bluetooth."""

from homeassistant.components.button import ButtonEntity

from .entity import InkbirdEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            *(InkbirdClearTarget(entry.runtime_data, probe) for probe in range(4)),
            InkbirdAcknowledgeAlarm(entry.runtime_data),
        ]
    )


class InkbirdClearTarget(InkbirdEntity, ButtonEntity):
    _attr_icon = "mdi:thermometer-off"

    def __init__(self, coordinator, probe):
        super().__init__(
            coordinator,
            f"probe{probe + 1}_clear_target",
            f"Probe {probe + 1} clear target",
        )
        self.probe = probe

    async def async_press(self):
        await self.coordinator.write_food_high(self.probe, None)


class InkbirdAcknowledgeAlarm(InkbirdEntity, ButtonEntity):
    _attr_icon = "mdi:bell-check"

    def __init__(self, coordinator):
        super().__init__(
            coordinator, "acknowledge_alarm", "Acknowledge temperature alarm"
        )

    async def async_press(self):
        await self.coordinator.acknowledge_alarm()
