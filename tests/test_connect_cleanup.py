"""Cleanup unsuccessful clients before a new power-cycle reconnect attempt."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator


@pytest.mark.asyncio
async def test_failed_connect_disconnects_client_even_if_not_connected(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    clients = [MagicMock(is_connected=False), MagicMock(is_connected=True)]
    for client in clients:
        client.disconnect = AsyncMock()
    factory = mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.BleakClientWithServiceCache",
        side_effect=clients,
    )
    calls = 0

    async def establish(create, device, name, **kwargs):
        nonlocal calls
        client = create(device, disconnected_callback=kwargs["disconnected_callback"])
        assert kwargs["max_attempts"] == 1
        calls += 1
        if calls == 1:
            raise TimeoutError
        return client

    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        side_effect=establish,
    )
    with pytest.raises(TimeoutError):
        await c._connect(MagicMock())
    clients[0].disconnect.assert_awaited_once()
    assert c._connecting_client is None and c.connect_cleanup_attempts == 1
    assert await c._connect(MagicMock()) is clients[1]
    assert factory.call_count == 2
    clients[1].disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_connection_releases_owned_client(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    client = MagicMock(is_connected=False, disconnect=AsyncMock())
    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.BleakClientWithServiceCache",
        return_value=client,
    )
    entered = asyncio.Event()

    async def establish(create, device, name, **kwargs):
        create(device)
        entered.set()
        await asyncio.Event().wait()

    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        side_effect=establish,
    )
    task = asyncio.create_task(c._connect(MagicMock()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.disconnect.assert_awaited_once()
    assert c._connecting_client is None


@pytest.mark.asyncio
async def test_cleanup_error_preserves_connect_error(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    client = MagicMock(disconnect=AsyncMock(side_effect=RuntimeError))
    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.BleakClientWithServiceCache",
        return_value=client,
    )

    async def establish(create, device, name, **kwargs):
        create(device)
        raise TimeoutError

    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        side_effect=establish,
    )
    with pytest.raises(TimeoutError):
        await c._connect(MagicMock())
    assert c.connect_cleanup_error == "RuntimeError"


def test_advertisement_does_not_skip_failed_connect_cooldown():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.connection_stage = "retrying"
    c._on_advertisement(MagicMock(), MagicMock())
    assert not c._retry_event.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, expected",
    [
        (TimeoutError(), "TimeoutError"),
        (
            RuntimeError("AA:BB:CC:DD:EE:FF via 192.168.1.2 " + "x" * 250),
            "[address] via [ip] " + "x" * 250,
        ),
    ],
)
async def test_failed_retry_reports_stage_type_and_redacted_detail(
    mocker, caplog, error, expected
):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_scanner_count",
        return_value=1,
    )
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(),
    )

    async def fail(device):
        c.connection_stage = "connecting"
        c._stop.set()
        raise error

    mocker.patch.object(c, "_session", side_effect=fail)
    await c._run()
    assert c.last_error == expected
    assert c.last_failure_stage == "connecting"
    assert c.last_error_type == type(error).__name__
    assert c.connection_events[-1]["reason"] == expected
    assert "ended at connecting" in caplog.text
    assert "AA:BB:CC:DD:EE:FF" not in caplog.text
    assert "192.168.1.2" not in caplog.text


@pytest.mark.asyncio
async def test_power_cycle_failed_retry_then_fresh_authenticated_session(mocker):
    from custom_components.inkbird_int14s_ble.protocol import frame

    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    clients = [MagicMock(is_connected=True) for _ in range(3)]

    async def write(uuid, payload, response):
        if payload[1] == 0xFB:
            c._on_frames(None, frame(0xFB, bytes(6)))
        elif payload[1] == 0xFC:
            c._on_frames(None, frame(0xFC, b"\x00"))

    for client in clients:
        client.disconnect = AsyncMock()
        client.start_notify = AsyncMock()
        client.write_gatt_char = AsyncMock(side_effect=write)
    factory = mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.BleakClientWithServiceCache",
        side_effect=clients,
    )
    attempts = 0

    async def establish(create, device, name, **kwargs):
        nonlocal attempts
        client = create(device)
        attempts += 1
        if attempts == 2:
            client.is_connected = False
            raise TimeoutError
        return client

    async def snapshot():
        assert c.available and c._auth.is_set()
        if attempts == 1:
            # Station powers off after its first authenticated session.
            clients[0].is_connected = False
            c._on_disconnect(clients[0])
        else:
            c._stop.set()

    real_wait = asyncio.wait_for

    async def fast_wait(awaitable, timeout):
        return await real_wait(awaitable, min(timeout, 0.01))

    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        side_effect=establish,
    )
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_scanner_count",
        return_value=1,
    )
    resolve = mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(),
    )
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.asyncio.wait_for",
        side_effect=fast_wait,
    )
    mocker.patch.object(c, "_snapshot", new=AsyncMock(side_effect=snapshot))
    await c._run()
    assert c.connection_attempts == 3 and c.successful_connections == 2
    assert factory.call_count == resolve.call_count == 3
    assert c.connect_cleanup_attempts == 1
    assert not c._disconnected.is_set()
    for client in clients:
        client.disconnect.assert_awaited_once()
