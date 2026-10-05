"""Register entities with the real HA platform and registries."""

import logging
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from custom_components.inkbird_int14s_ble import (
    binary_sensor,
    button,
    number,
    select,
    sensor,
)
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.registry import (
    async_link_station_entities,
    async_remove_legacy_target_text,
    async_update_station_firmware,
    async_watch_station_entities,
    registration_diagnostics,
)
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
@pytest.mark.parametrize("unlink", [False, True])
async def test_real_entity_registration(tmp_path, unlink):
    integration = Path(__file__).parents[1] / "custom_components/inkbird_int14s_ble"
    shutil.copytree(integration, tmp_path / "custom_components/inkbird_int14s_ble")
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    loader.async_setup(hass)
    frame.async_setup(hass)
    entry = MockConfigEntry(
        domain="inkbird_int14s_ble", data={"address": "AA:BB:CC:DD:EE:FF"}
    )
    entry.add_to_hass(hass)
    entry.runtime_data = InkbirdCoordinator(hass, entry.data["address"])
    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    platforms = []
    try:
        for domain, module, count in [
            ("sensor", sensor, 35),
            ("number", number, 5),
            ("button", button, 5),
            ("binary_sensor", binary_sensor, 5),
            ("select", select, 1),
        ]:
            platform = EntityPlatform(
                hass=hass,
                logger=logging.getLogger(__name__),
                domain=domain,
                platform_name="inkbird_int14s_ble",
                platform=module,
                scan_interval=timedelta(seconds=30),
                entity_namespace=None,
            )
            platform.config_entry = entry
            platforms.append(platform)
            add = MagicMock()
            await module.async_setup_entry(hass, entry, add)
            await platform.async_add_entities(add.call_args.args[0])
            assert len(platform.entities) == count
            assert len(hass.states.async_all(domain)) == count
            assert all(
                state.state == "unavailable" for state in hass.states.async_all(domain)
            )
        devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        assert len(devices) == 1
        registered = er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        assert len(registered) == 51
        assert all(entity.device_id == devices[0].id for entity in registered)
        before_ids = {entity.entity_id for entity in registered}
        if unlink:
            for entity in registered:
                er.async_get(hass).async_update_entity(entity.entity_id, device_id=None)
            assert registration_diagnostics(hass, entry)["unlinked_entity_count"] == 51
        async_link_station_entities(hass, entry)
        registered = er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        assert {entity.entity_id for entity in registered} == before_ids
        assert all(entity.device_id == devices[0].id for entity in registered)
        diagnostics = registration_diagnostics(hass, entry)
        assert diagnostics["entity_count"] == 51
        assert diagnostics["unlinked_entity_count"] == 0
        assert diagnostics["device_entity_counts"] == {devices[0].id: 51}
        entry.runtime_data.station_firmware = "V1.0.2"
        async_update_station_firmware(hass, entry)
        assert dr.async_get(hass).async_get(devices[0].id).sw_version == "V1.0.2"
        for probe in range(1, 5):
            er.async_get(hass).async_get_or_create(
                "text",
                "inkbird_int14s_ble",
                f"{entry.runtime_data.address}_probe{probe}_food_high",
                config_entry=entry,
                device_id=devices[0].id,
            )
        assert registration_diagnostics(hass, entry)["entity_count"] == 55
        async_remove_legacy_target_text(hass, entry)
        assert registration_diagnostics(hass, entry)["entity_count"] == 51
        unwatch = async_watch_station_entities(hass, entry)
        try:
            # New controls can be registered after the initial setup repair.
            late = er.async_get(hass).async_get_or_create(
                "button",
                "inkbird_int14s_ble",
                "late_control",
                config_entry=entry,
            )
            assert late.device_id is None
            await hass.async_block_till_done()
            assert (
                er.async_get(hass).async_get(late.entity_id).device_id == devices[0].id
            )
            controls = [
                entity for entity in registered if entity.domain in ("number", "button")
            ]
            for control in controls:
                er.async_get(hass).async_update_entity(
                    control.entity_id, device_id=None
                )
            await hass.async_block_till_done()
            assert all(
                er.async_get(hass).async_get(control.entity_id).device_id
                == devices[0].id
                for control in controls
            )
            er.async_get(hass).async_remove(late.entity_id)
            await hass.async_block_till_done()
            assert registration_diagnostics(hass, entry)["entities_by_domain"] == {
                "binary_sensor": {"total": 5, "linked": 5},
                "button": {"total": 5, "linked": 5},
                "number": {"total": 5, "linked": 5},
                "sensor": {"total": 35, "linked": 35},
                "select": {"total": 1, "linked": 1},
            }
        finally:
            unwatch()
    finally:
        for platform in platforms:
            await platform.async_reset()
        await hass.async_stop()
