"""Twenty probe channels, station/batteries and four Time to Temp estimates."""

from time import time

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory

from .entity import InkbirdEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = []
    for probe in range(4):
        for channel in range(4):
            entities.append(
                InkbirdSensor(
                    coordinator,
                    f"probe{probe + 1}_food{channel + 1}",
                    f"Probe {probe + 1} food {channel + 1} temperature",
                    "temperature",
                    lambda p=probe, c=channel: coordinator.food[p][c],
                )
            )
        entities.append(
            InkbirdSensor(
                coordinator,
                f"probe{probe + 1}_ambient",
                f"Probe {probe + 1} ambient temperature",
                "temperature",
                lambda p=probe: coordinator.ambient[p],
            )
        )
        entities.append(
            InkbirdSensor(
                coordinator,
                f"probe{probe + 1}_eta",
                f"Probe {probe + 1} time to temp",
                "duration",
                lambda p=probe: coordinator.eta(p),
            )
        )
    entities.append(
        InkbirdSensor(
            coordinator,
            "station_temperature",
            "Station temperature",
            "temperature",
            lambda: coordinator.station_temperature,
        )
    )
    for index in range(5):
        name = "Station battery" if index == 0 else f"Probe {index} battery"
        entities.append(
            InkbirdSensor(
                coordinator,
                f"battery{index}",
                name,
                "battery",
                lambda i=index: coordinator.batteries[i],
            )
        )
    entities.append(InkbirdFirmware(coordinator, None))
    entities.extend(InkbirdFirmware(coordinator, probe) for probe in range(4))
    async_add_entities(entities)


class InkbirdFirmware(InkbirdEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, probe):
        self._probe = probe
        key = "station_firmware" if probe is None else f"probe{probe + 1}_firmware"
        name = "Station firmware" if probe is None else f"Probe {probe + 1} firmware"
        super().__init__(coordinator, key, name)

    @property
    def native_value(self):
        return (
            self.coordinator.station_firmware
            if self._probe is None
            else self.coordinator.probe_firmware[self._probe]
        )


class InkbirdSensor(InkbirdEntity, SensorEntity):
    def __init__(self, coordinator, key, name, kind, getter):
        super().__init__(coordinator, key, name)
        self._getter = getter
        self._kind = kind
        self._attr_device_class = SensorDeviceClass(kind)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = {
            "temperature": "°F",
            "battery": "%",
            "duration": "min",
        }[kind]
        self._attr_suggested_display_precision = 1 if kind != "battery" else 0
        if kind == "battery":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        if (
            self._kind == "temperature"
            and time() - self.coordinator._last_temperature > 90
        ):
            return None
        return self._getter()
