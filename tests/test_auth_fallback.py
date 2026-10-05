"""Missing ACK may allow reads; explicit authentication gates writes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.protocol import frame
from homeassistant.exceptions import HomeAssistantError
from test_ble import temperatures


@pytest.mark.asyncio
@pytest.mark.parametrize("state_verified", [False, True])
async def test_missing_ack_reads_and_state_flag_controls_writes(mocker, state_verified):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    client = MagicMock(is_connected=True)

    async def write(uuid, payload, response):
        if payload[1] == 0xFB:
            c._on_frames(None, frame(0xFB, bytes(6)))

    async def snapshot():
        c._on_temperature(None, temperatures())
        c._on_state(None, bytes([1, 16] * 4 + [1, int(state_verified), 0]))
        c._stop.set()

    real_wait_for = asyncio.wait_for

    async def fast_wait(awaitable, timeout):
        return await real_wait_for(awaitable, min(timeout, 0.01))

    client.start_notify = AsyncMock()
    client.write_gatt_char = AsyncMock(side_effect=write)
    client.disconnect = AsyncMock()
    mocker.patch(
        "custom_components.inkbird_int14s_ble._vendor.int14s.client.establish_connection",
        new=AsyncMock(return_value=client),
    )
    mocker.patch(
        "custom_components.inkbird_int14s_ble.coordinator.asyncio.wait_for",
        side_effect=fast_wait,
    )
    mocker.patch.object(c, "_snapshot", new=AsyncMock(side_effect=snapshot))
    observed = []

    def on_update():
        if c.available:
            observed.append(c._auth.is_set())
            if not state_verified:
                with pytest.raises(HomeAssistantError):
                    c._require_auth()
            else:
                c._require_auth()

    c.async_add_listener(on_update)
    await c._session(MagicMock())
    assert observed and all(value is state_verified for value in observed)
    assert c.authentication_status == (
        "confirmed_by_state" if state_verified else "streaming_without_ack_read_only"
    )
    assert c.food[0][0] == 70 and c.base_charging is True


def test_rejection_cannot_be_overridden_by_state_or_late_ack():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._verification_sent = True
    c._on_frames(None, frame(0xFC, b"\x01"))
    c._on_state(None, bytes([1, 16] * 4 + [1, 1, 0]))
    c._on_frames(None, frame(0xFC, b"\x00"))
    assert not c._auth.is_set() and not c.available
    assert c.authentication_status == "rejected"


def test_state_flag_before_verification_does_not_authenticate():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_state(None, bytes([1, 16] * 4 + [1, 1, 0]))
    assert not c._auth.is_set()
