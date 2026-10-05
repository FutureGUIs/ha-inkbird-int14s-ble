"""Public library boundary and compatibility with existing HA configuration."""

from unittest.mock import MagicMock

import pytest
from custom_components.inkbird_int14s_ble._vendor.int14s import INT14SBWClient
from custom_components.inkbird_int14s_ble.config_flow import InkbirdConfigFlow
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.asyncio
async def test_coordinator_uses_library_and_maps_write_errors_to_ha():
    coordinator = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    assert isinstance(coordinator, INT14SBWClient)
    with pytest.raises(HomeAssistantError, match="authenticated"):
        await coordinator.write_food_high(0, 165)


@pytest.mark.asyncio
async def test_manual_address_validation_remains_available(mocker):
    mocker.patch(
        "custom_components.inkbird_int14s_ble.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    )
    flow = InkbirdConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_entries.return_value = []
    show = mocker.patch.object(flow, "async_show_form", return_value={})
    await flow.async_step_user({CONF_ADDRESS: "not-a-bluetooth-address"})
    assert show.call_args.kwargs["errors"] == {CONF_ADDRESS: "invalid_address"}
