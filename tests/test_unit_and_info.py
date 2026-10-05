"""Unit control and firmware-info capture queries."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.protocol import frame, snapshot_frames
from custom_components.inkbird_int14s_ble.select import InkbirdTemperatureUnit
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.asyncio
@pytest.mark.parametrize("unit,option", [("C", "Celsius"), ("F", "Fahrenheit")])
async def test_unit_write_and_confirmed_readback(unit, option):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    entity = InkbirdTemperatureUnit(c)
    assert entity.current_option is None
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option(option)
    c.available = True
    c._auth.set()

    async def write(payload):
        if payload == frame(4):
            c._on_frames(None, frame(4, unit.encode("ascii")))

    c._write = AsyncMock(side_effect=write)
    await entity.async_select_option(option)
    assert [call.args[0] for call in c._write.call_args_list] == [
        frame(3, unit.encode("ascii")),
        frame(4),
    ]
    assert entity.current_option == option
    assert entity.extra_state_attributes["write_status"] == "confirmed_by_readback"
    assert frame(4) in snapshot_frames()


@pytest.mark.asyncio
async def test_unit_readback_mismatch_and_invalid_report():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.available = True
    c._auth.set()

    async def write(payload):
        if payload == frame(4):
            c._on_frames(None, frame(4, b"F"))

    c._write = AsyncMock(side_effect=write)
    await c.write_temperature_unit("C")
    assert c.temperature_unit == "F" and c.unit_write_status == "readback_mismatch"
    c._on_frames(None, frame(4, b"X"))
    assert c.temperature_unit == "F"
    with pytest.raises(HomeAssistantError):
        await c.write_temperature_unit("Kelvin")


@pytest.mark.parametrize("size", [20, 200])
def test_fragmented_device_info_is_captured_without_guessing_version(size):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    payload = bytes(range(size))
    raw = frame(0x15, payload)
    c._on_frames(None, raw[:8])
    assert not c._device_info_received
    c._on_frames(None, raw[8:])
    assert c._device_info_received
    assert c.device_info_payload_hex == payload.hex()
    assert c.device_info_payload_length == size


@pytest.mark.asyncio
async def test_device_info_retries_are_capped_and_stop_after_response(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._client = MagicMock()
    c._client.read_gatt_char = AsyncMock(side_effect=RuntimeError)
    c._write = AsyncMock()
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.asyncio.sleep",
        new=AsyncMock(),
    )
    for _ in range(4):
        await c._snapshot()
    assert c._device_info_requests == 3
    assert sum(call.args[0] == frame(0x15) for call in c._write.call_args_list) == 3
    c._device_info_requests = 0
    c._on_frames(None, frame(0x15, b"\x01\x02"))
    await c._snapshot()
    assert c._device_info_requests == 0
