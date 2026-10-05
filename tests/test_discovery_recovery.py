"""Discovery events wake a waiting station connection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator


@pytest.mark.asyncio
async def test_discovery_wakes_wait_without_ten_second_delay(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.hass.async_create_background_task.side_effect = lambda coro, name: (
        asyncio.create_task(coro)
    )
    unwatch = MagicMock()
    register = mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_register_callback",
        return_value=unwatch,
    )
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_scanner_count",
        return_value=1,
    )
    resolve = mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_ble_device_from_address",
        side_effect=[None, MagicMock()],
    )

    async def session(device):
        c._stop.set()

    session_mock = mocker.patch.object(
        c, "_session", new=AsyncMock(side_effect=session)
    )
    await c.async_start()
    await asyncio.sleep(0)
    assert c.connection_stage == "waiting_for_station"
    session_mock.assert_not_awaited()
    register.call_args.args[1](MagicMock(), MagicMock())
    await asyncio.wait_for(c._task, 0.5)
    session_mock.assert_awaited_once()
    assert resolve.call_count == 2 and c.discovery_wakeups == 1
    assert register.call_args.args[2] == {"address": c.address, "connectable": True}
    await c.async_stop()
    unwatch.assert_called_once()


def test_discovery_does_not_interrupt_connected_session_or_connect_attempt():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    for stage in ("connecting", "connected_authenticated", "stopped"):
        c.connection_stage = stage
        c._on_advertisement(MagicMock(), MagicMock())
    assert not c._retry_event.is_set() and c.discovery_wakeups == 0
