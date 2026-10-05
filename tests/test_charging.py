"""Compact state flags and charging entity freshness."""

from unittest.mock import MagicMock

import pytest
from custom_components.inkbird_int14s_ble.binary_sensor import (
    InkbirdCharging,
    async_setup_entry,
)
from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator


@pytest.mark.asyncio
async def test_charging_entities_and_flags():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    add = MagicMock()
    await async_setup_entry(None, MagicMock(runtime_data=c), add)
    entities = add.call_args.args[0]
    assert len(entities) == 5
    assert all(e.is_on is None and not e.available for e in entities)
    c.available = True
    # Probe flags alternate charging and undocked; base plugged in.
    c._on_state(None, bytes([3, 16, 1, 16, 3, 16, 1, 16, 1, 4, 0]))
    assert [e.is_on for e in entities] == [True, False, True, False, True]
    assert entities[0].name == "Probe 1 charging"
    assert entities[-1].name == "Station charging"
    assert entities[-1].unique_id == f"{c.address}_base_charging"
    assert all(
        e.device_info["identifiers"] == {("inkbird_int14s_ble", c.address)}
        for e in entities
    )
    c._on_state(None, bytes([1, 16] * 4 + [0, 4, 0]))
    assert [e.is_on for e in entities] == [False] * 5
    c.available = False
    assert all(not e.available for e in entities)


def test_state_flags_ignore_other_bits_and_bad_packets(mocker):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_state(None, bytes([0xFD, 16] * 4 + [0xFE, 4, 0]))
    assert c.probe_charging == [False] * 4 and c.base_charging is False
    timestamp = c._last_state
    c._on_state(None, b"")
    assert c._last_state == timestamp and c.probe_charging == [False] * 4
    mocker.patch(
        "custom_components.inkbird_int14s_ble.binary_sensor.time",
        return_value=timestamp + 91,
    )
    assert InkbirdCharging(c, 0).is_on is None
    assert InkbirdCharging(c, None).is_on is None


def test_charging_clears_probe_temperature_and_trend():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.food[0] = [70] * 4
    c.ambient[0] = 75
    c.trends[0].add(1, 70)
    c._on_state(None, bytes([3, 16] + [1, 16] * 3 + [0, 4, 0]))
    assert c.food[0] == [None] * 4 and c.ambient[0] is None
    assert not c.trends[0].samples


def test_short_dock_packets_update_only_present_flags():
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_state(None, bytes([3, 16, 1, 16, 3, 16, 1, 16, 1]))
    assert c.probe_charging == [True, False, True, False]
    assert c.base_charging is True
    base_timestamp = c._base_state_time
    other_timestamp = c._probe_state_times[1]
    c._on_state(None, b"\x01")
    assert c.probe_charging == [False, False, True, False]
    assert c._base_state_time == base_timestamp
    assert c._probe_state_times[1] == other_timestamp
    c2 = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c2._on_state(None, b"\x03")
    assert c2.probe_charging == [True, None, None, None]
    assert InkbirdCharging(c2, None).is_on is None


def test_dock_mask_survives_next_temperature_packet():
    from test_ble import temperatures

    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_state(None, bytes([3, 16] + [1, 16] * 3))
    c._on_temperature(None, temperatures())
    assert c.food[0] == [None] * 4 and c.ambient[0] is None
    assert c.food[1][0] == 71
    assert not c.trends[0].samples
    c._on_state(None, b"\x01")
    c._on_temperature(None, temperatures())
    assert c.food[0][0] == 70


def test_int14s_15_byte_state_uses_three_byte_probe_blocks():
    from test_ble import temperatures

    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    # First 11 bytes come from the owner's diagnostics. The four remaining
    # bytes are synthetic: the 0.1.10 diagnostic capture truncated them.
    raw = bytes.fromhex("011000071000071000011000ffff01")
    assert len(raw) == 15
    c._verification_sent = True
    c._on_state(None, raw)
    assert c.probe_charging == [False, True, True, False]
    assert c.base_charging is True and c._base_state_time > 0
    assert not c._auth.is_set()  # Extended layout cannot confirm auth yet.
    assert c.last_state_hex == raw.hex()
    assert c.state_layout == "int14s_three_byte_probe_blocks"
    c._on_temperature(None, temperatures())
    assert c.food[0][0] == 70 and c.food[3][0] == 73
    assert c.food[1] == c.food[2] == [None] * 4
    assert [InkbirdCharging(c, p).is_on for p in range(4)] == [False, True, True, False]
    assert InkbirdCharging(c, None).is_on is True


@pytest.mark.parametrize(
    "packet,expected",
    [
        ("031000071000071000071000530500", True),
        ("011000011000011000011000520500", False),
    ],
)
def test_owner_charging_and_unplugged_captures(packet, expected):
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c.available = True
    c._on_state(None, bytes.fromhex(packet))
    assert c.probe_charging == [expected] * 4
    assert c.base_charging is expected
    assert InkbirdCharging(c, None).is_on is expected
    assert c.last_error is None
