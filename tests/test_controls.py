"""Authenticated target clearing, brightness and alarm acknowledgement."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble.button import (
    InkbirdAcknowledgeAlarm,
    InkbirdClearTarget,
)
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.number import InkbirdTarget
from custom_components.inkbird_int14s_ble.protocol import (
    food_high_frames,
    frame,
    target_report,
)
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.parametrize("probe", range(4))
def test_clear_frames(probe):
    commands = food_high_frames(probe, None)
    assert commands[0] == bytes([9, 1, 1 << probe, 0, 0, 0, 0, 0, 0, 0])
    assert target_report(commands[0][2:]) == (probe, None)


@pytest.mark.asyncio
async def test_clear_button_confirms_off_and_discards_target(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.targets[0] = 165
    c.available = True
    c._auth.set()
    client = MagicMock()
    client.is_connected = True
    client.services.get_characteristic.return_value.properties = ["write"]

    async def write(uuid, payload, response):
        if payload[1] == 2:
            c._on_frames(None, frame(2, food_high_frames(0, None)[0][2:]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    c._client = client
    await InkbirdClearTarget(c, 0).async_press()
    assert c.targets[0] is None
    assert c.write_status[0] == "confirmed_by_readback"
    assert c.eta(0) is None
    target = InkbirdTarget(c, 0)
    assert target.native_value is None and target.name == "Probe 1 target"
    mocker.patch(
        "custom_components.inkbird_int14s_ble.entity.InkbirdEntity.async_added_to_hass",
        new=AsyncMock(),
    )
    mocker.patch.object(
        target,
        "async_get_last_number_data",
        new=AsyncMock(return_value=MagicMock(native_value=None)),
    )
    await target.async_added_to_hass()
    assert target.native_value is None


@pytest.mark.asyncio
async def test_brightness_exact_command_and_readback():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.available = True
    c._auth.set()
    client = MagicMock()
    client.is_connected = True
    client.services.get_characteristic.return_value.properties = ["write"]

    async def write(uuid, payload, response):
        if payload == b"\x01\x06":
            c._on_frames(None, b"\x02\x06\x50")

    client.write_gatt_char = AsyncMock(side_effect=write)
    c._client = client
    await c.write_brightness(80)
    assert c.brightness == 80
    assert c.brightness_write_status == "confirmed_by_readback"
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == [
        b"\x02\x05\x50",
        b"\x01\x06",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 101, 80.5, True, float("nan"), float("inf")])
async def test_invalid_brightness_never_writes(value):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._write = AsyncMock()
    with pytest.raises(HomeAssistantError):
        await c.write_brightness(value)
    c._write.assert_not_awaited()


@pytest.mark.asyncio
async def test_ack_requires_auth_and_preserves_targets():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._write = AsyncMock()
    button = InkbirdAcknowledgeAlarm(c)
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    c._write.assert_not_awaited()
    c.targets[0] = 165
    c.available = True
    c._auth.set()
    await button.async_press()
    c._write.assert_awaited_once_with(b"\x02\x0d\x0f")
    assert c.targets[0] == 165
