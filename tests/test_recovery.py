"""Regression checks for intermittent Bluetooth failures."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble.const import CHR_FF02
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.protocol import frame
from test_ble import temperatures


def test_bad_temperature_packet_preserves_last_valid_sample():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_temperature(None, temperatures())
    timestamp = c._last_temperature
    samples = list(c.trends[0].samples)
    c._on_temperature(None, b"\x00")
    assert c.food[0][0] == 70
    assert c._last_temperature == timestamp
    assert list(c.trends[0].samples) == samples
    assert c.invalid_temperature_packets == 1


def test_disconnect_blocks_controls_and_wakes_recovery():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    client = MagicMock()
    c._client = client
    c.available = True
    c._auth.set()
    c._on_disconnect(MagicMock())
    assert c.available
    c._on_disconnect(client)
    assert not c.available and not c._auth.is_set()
    assert c._disconnected.is_set()


@pytest.mark.asyncio
async def test_one_failed_poll_does_not_reconnect(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    client = MagicMock(is_connected=True)
    callbacks = {}

    async def subscribe(uuid, callback):
        callbacks[uuid] = callback

    async def write(uuid, payload, response):
        if payload[1] == 0xFB:
            callbacks[CHR_FF02](None, frame(0xFB, bytes(6)))
        elif payload[1] == 0xFC:
            callbacks[CHR_FF02](None, frame(0xFC, b"\x00"))

    calls = 0

    async def snapshot():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        assert c.available and c._auth.is_set()
        c._stop.set()

    async def wait(event, timeout):
        # Authentication events are already set; polling wait need not take 10s.
        if timeout == 10:
            event.close()
            raise TimeoutError
        return await event

    client.start_notify = AsyncMock(side_effect=subscribe)
    client.write_gatt_char = AsyncMock(side_effect=write)
    client.disconnect = AsyncMock()
    connector = mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        new=AsyncMock(return_value=client),
    )
    mocker.patch.object(c, "_snapshot", new=AsyncMock(side_effect=snapshot))
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.asyncio.wait_for",
        side_effect=wait,
    )
    c._on_temperature(None, temperatures())
    await c._session(MagicMock())
    assert calls == 2 and c.poll_failures == 1
    assert c.successful_connections == 1
    assert c.food[0][0] == 70
    connector.assert_awaited_once()
    assert connector.call_args.kwargs["disconnected_callback"] == c._on_disconnect


@pytest.mark.asyncio
async def test_failed_connect_preserves_diagnostic_values(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_temperature(None, temperatures())
    c._on_battery(None, bytes([80, 90, 91, 92, 93]))
    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        new=AsyncMock(side_effect=TimeoutError),
    )
    with pytest.raises(TimeoutError):
        await c._session(MagicMock())
    assert not c.available
    assert c.food[0][0] == 70 and c.batteries[0] == 80
    assert c.connection_attempts == 1
