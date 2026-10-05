"""Repair station links for this config entry's existing entities."""

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .entity import station_device_info


@callback
def async_update_station_firmware(hass, entry):
    firmware = entry.runtime_data.station_firmware
    if firmware:
        registry = dr.async_get(hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, entry.runtime_data.address), entry.entry_id
        )
        if device and device.sw_version != firmware:
            registry.async_update_device(device.id, sw_version=firmware)


@callback
def async_remove_legacy_target_text(hass, entry):
    registry = er.async_get(hass)
    target_ids = {
        f"{entry.runtime_data.address}_probe{probe}_food_high" for probe in range(1, 5)
    }
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity.platform == DOMAIN
            and entity.domain == "text"
            and entity.unique_id in target_ids
        ):
            registry.async_remove(entity.entity_id)


@callback
def async_link_station_entities(hass, entry):
    registry = er.async_get(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **station_device_info(entry.runtime_data.address),
    )
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform == DOMAIN and entity.device_id != device.id:
            registry.async_update_entity(entity.entity_id, device_id=device.id)


@callback
def async_watch_station_entities(hass, entry):
    """Keep late-created controls linked, including platform setup retries."""
    registry = er.async_get(hass)

    @callback
    def update(event):
        if event.data.get("action") not in ("create", "update"):
            return
        entity = registry.async_get(event.data.get("entity_id", ""))
        if (
            entity
            and entity.config_entry_id == entry.entry_id
            and entity.platform == DOMAIN
        ):
            async_link_station_entities(hass, entry)

    return hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, update)


@callback
def registration_diagnostics(hass, entry):
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    return {
        "entity_count": len(entities),
        "entities_by_domain": {
            domain: {
                "total": sum(entity.domain == domain for entity in entities),
                "linked": sum(
                    entity.domain == domain
                    and entity.device_id in {device.id for device in devices}
                    for entity in entities
                ),
            }
            for domain in sorted({entity.domain for entity in entities})
        },
        "unlinked_entity_count": sum(entity.device_id is None for entity in entities),
        "device_entity_counts": {
            device.id: sum(entity.device_id == device.id for entity in entities)
            for device in devices
        },
        "hidden_entity_count": sum(entity.hidden_by is not None for entity in entities),
        "disabled_entity_count": sum(
            entity.disabled_by is not None for entity in entities
        ),
    }
