"""Protocol vectors and simulated Bluetooth reads/writes; no hardware access."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble import async_setup_entry as setup_integration
from custom_components.inkbird_int14s_ble.auth import build_verify_response
from custom_components.inkbird_int14s_ble.config_flow import _is_supported
from custom_components.inkbird_int14s_ble.const import CHR_BATTERY, CHR_FF01, CHR_FF02
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.number import InkbirdTarget
from custom_components.inkbird_int14s_ble.number import (
    async_setup_entry as setup_numbers,
)
from custom_components.inkbird_int14s_ble.protocol import (
    battery_payload,
    food_high_frames,
    frame,
    target_report,
    temperature_payload,
)
from custom_components.inkbird_int14s_ble.sensor import (
    async_setup_entry as setup_sensors,
)
from custom_components.inkbird_int14s_ble.trend import TemperatureTrend
from homeassistant.exceptions import HomeAssistantError


def temperatures():
    raw = bytearray(54)
    for probe in range(4):
        for channel in range(5):
            offset = probe * 13 + 2 + channel * 2
            raw[offset : offset + 2] = (
                7000 + probe * 100 + channel if channel < 4 else 900 + probe
            ).to_bytes(2, "little", signed=True)
    raw[52:54] = (720).to_bytes(2, "little", signed=True)
    return bytes(raw)


def test_auth_known_capture(mocker):
    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.auth.time.time",
        return_value=1779980959.482,
    )
    assert (
        build_verify_response(bytes.fromhex("2a19e11e78aa")).hex()
        == "08fce2019f5a186a78"
    )


@pytest.mark.parametrize("probe,mask", [(0, 1), (1, 2), (2, 4), (3, 8)])
def test_food_write_frames(probe, mask):
    frames = food_high_frames(probe, 60)
    assert frames[0] == bytes([9, 1, mask, 16, 0x58, 2, 0, 0, 0, 0])
    assert frames[1] == bytes([6, 0x23, mask, 0, 0, 0, 0])
    assert target_report(frames[0][2:]) == (probe, 60)


@pytest.mark.parametrize("value", [31, 213, True, float("nan"), float("inf"), "60"])
def test_invalid_target(value):
    with pytest.raises(ValueError):
        food_high_frames(0, value)


def test_multisensor_layout_and_sentinels():
    food, ambient, station = temperature_payload(temperatures())
    assert food[0] == [70, 70.01, 70.02, 70.03]
    assert food[3] == [73, 73.01, 73.02, 73.03]
    assert ambient == [90, 90.1, 90.2, 90.3]
    assert station == 72
    raw = bytearray(temperatures())
    raw[2:4] = b"\xff\x7f"
    assert temperature_payload(raw)[0][0][0] is None
    with pytest.raises(ValueError):
        temperature_payload(raw + b"\x00")


def test_batteries():
    assert battery_payload(bytes([75, 100, 127, 101, 0])) == [75, 100, None, None, 0]
    with pytest.raises(ValueError):
        battery_payload(bytes(3))


def test_fragmented_frames_and_readback():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    raw = frame(0xFB, bytes(6)) + frame(0xFC, b"\x00")
    c._on_frames(None, raw[:4])
    assert not c._challenge_event.is_set()
    c._on_frames(None, raw[4:])
    assert c._auth.is_set()
    target = food_high_frames(2, 165)[0]
    c._on_frames(None, frame(2, target[2:]))
    assert c.targets[2] == 165 and c.target_sources[2] == "device_report"
    assert c.report_sequences[2] == 1


@pytest.mark.asyncio
async def test_write_waits_for_auth_and_reports_confirmation(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    with pytest.raises(HomeAssistantError):
        await c.write_food_high(0, 60)
    client = MagicMock()
    client.is_connected = True
    client.services.get_characteristic.return_value.properties = [
        "write",
        "write-without-response",
    ]

    async def write(uuid, payload, response):
        if payload[1] == 2:
            c._on_frames(None, frame(2, food_high_frames(0, 60)[0][2:]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    c._client = client
    c.available = True
    c._auth.set()
    await c.write_food_high(0, 60)
    assert c.write_status[0] == "confirmed_by_readback"
    assert c.targets[0] == 60 and c.target_sources[0] == "device_report"
    assert [call.args[1][1] for call in client.write_gatt_char.call_args_list] == [
        1,
        0x23,
        2,
    ]
    assert all(
        call.kwargs["response"] for call in client.write_gatt_char.call_args_list
    )


@pytest.mark.asyncio
async def test_session_authenticates_then_reads_without_network(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    client = MagicMock()
    client.is_connected = True
    callbacks = {}

    async def subscribe(uuid, callback):
        callbacks[uuid] = callback

    async def write(uuid, payload, response):
        if payload[1] == 0xFB:
            callbacks[CHR_FF02](None, frame(0xFB, bytes(6)))
        elif payload[1] == 0xFC:
            callbacks[CHR_FF02](None, frame(0xFC, b"\x00"))

    async def read(uuid):
        if uuid == CHR_FF01:
            return temperatures()
        if uuid == CHR_BATTERY:
            c._stop.set()
            return bytes([80, 90, 91, 92, 93])
        return bytes([1, 16] * 4 + [0, 4, 0])

    client.start_notify = AsyncMock(side_effect=subscribe)
    client.write_gatt_char = AsyncMock(side_effect=write)
    client.read_gatt_char = AsyncMock(side_effect=read)
    client.disconnect = AsyncMock()
    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        new=AsyncMock(return_value=client),
    )
    await c._session(MagicMock())
    assert c.food[0][0] == 70 and c.batteries == [80, 90, 91, 92, 93]
    assert c._client is None and not c._auth.is_set()
    client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_sensor_count_and_restored_target(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    add = MagicMock()
    await setup_sensors(None, MagicMock(runtime_data=c), add)
    assert len(add.call_args.args[0]) == 35
    target = InkbirdTarget(c, 0)
    mocker.patch(
        "custom_components.inkbird_int14s_ble.entity.InkbirdEntity.async_added_to_hass",
        new=AsyncMock(),
    )
    mocker.patch.object(
        target,
        "async_get_last_number_data",
        new=AsyncMock(return_value=MagicMock(native_value=165)),
    )
    await target.async_added_to_hass()
    assert target.native_value == 165
    assert target.extra_state_attributes["value_source"] == "restored_last_requested"


@pytest.mark.parametrize(
    "name", ["INT-14S-BW", "Int14sbw", "INT14SBW", "INT14Sbw-device"]
)
def test_advertisement_names(name):
    assert _is_supported(SimpleNamespace(name=name))


def test_trend_and_configuration_are_ble_only():
    trend = TemperatureTrend()
    for minute in range(6):
        trend.add(minute * 60, 100 + minute * 2)
    assert trend.minutes_to_target(130, 300) == 10
    assert trend.minutes_to_target(130, 391) is None
    root = Path(__file__).parents[1] / "custom_components/inkbird_int14s_ble"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["dependencies"] == ["bluetooth"]
    assert "tinytuya" not in " ".join(manifest["requirements"])
    for path in root.glob("*.py"):
        assert "tinytuya" not in path.read_text()
    strings = json.loads((root / "strings.json").read_text())
    assert set(strings["config"]["step"]["user"]["data"]) == {"address"}


@pytest.mark.asyncio
async def test_entry_registers_all_entities_before_connection_without_scanner(mocker):
    mocker.patch("custom_components.inkbird_int14s_ble.async_watch_station_entities")
    mocker.patch("custom_components.inkbird_int14s_ble.async_link_station_entities")
    mocker.patch("custom_components.inkbird_int14s_ble.async_remove_legacy_target_text")
    hass = MagicMock()
    entry = MagicMock(data={"address": "AA:BB:CC:DD:EE:FF"})
    add_sensors = MagicMock()
    add_numbers = MagicMock()
    start = mocker.patch.object(InkbirdCoordinator, "async_start", new=AsyncMock())
    scanner_count = mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_scanner_count",
        return_value=0,
    )

    async def forward(config_entry, platforms):
        start.assert_not_awaited()
        await setup_sensors(hass, config_entry, add_sensors)
        await setup_numbers(hass, config_entry, add_numbers)

    hass.config_entries.async_forward_entry_setups = AsyncMock(side_effect=forward)
    assert await setup_integration(hass, entry)
    sensors = add_sensors.call_args.args[0]
    numbers = list(add_numbers.call_args.args[0])
    assert len(sensors) == 35 and len(numbers) == 5
    assert all(
        entity.unique_id and not entity.available for entity in sensors + numbers
    )
    start.assert_awaited_once()
    scanner_count.assert_not_called()


@pytest.mark.asyncio
async def test_missing_scanner_retries_and_recovers(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_scanner_count",
        side_effect=[0, 1],
    )
    observed_errors = []
    c.async_add_listener(lambda: observed_errors.append(c.last_error))

    async def session(device):
        c._stop.set()

    session_mock = mocker.patch.object(
        c, "_session", new=AsyncMock(side_effect=session)
    )

    async def wait(waiter, timeout):
        if c._stop.is_set():
            return await waiter
        waiter.close()
        raise TimeoutError

    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.asyncio.wait_for",
        side_effect=wait,
    )
    await c._run()
    assert (
        observed_errors[0] == "No connectable Bluetooth adapter or proxy is available"
    )
    session_mock.assert_awaited_once()
