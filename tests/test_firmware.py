"""Version fields at the offsets observed in the owner's device-info capture."""

from unittest.mock import MagicMock

from custom_components.inkbird_int14s_ble.coordinator import InkbirdCoordinator
from custom_components.inkbird_int14s_ble.protocol import firmware_versions, frame
from custom_components.inkbird_int14s_ble.sensor import InkbirdFirmware


def test_captured_version_layout_and_firmware_entities():
    # Address/ID bytes are replaced by zeros; retain the captured version fields.
    payload = bytearray(75)
    for offset, version in zip(
        (10, 23, 36, 49, 62),
        (b"V1.0.2", b"V1.3.1", b"V1.3.1", b"V1.3.1", b"V1.3.1"),
        strict=True,
    ):
        payload[offset : offset + 6] = version
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_frames(None, frame(0x15, payload))
    assert c.station_firmware == "V1.0.2"
    assert c.probe_firmware == ["V1.3.1"] * 4
    assert InkbirdFirmware(c, None).native_value == "V1.0.2"
    assert [InkbirdFirmware(c, p).native_value for p in range(4)] == ["V1.3.1"] * 4
    assert c.firmware_decode_status == "decoded_int14s_75_byte_layout"


def test_unknown_firmware_layouts_are_not_guessed():
    for payload in (b"", bytes(74), bytes(75), bytes(76)):
        assert firmware_versions(payload) is None
    c = InkbirdCoordinator(MagicMock(), "AA:BB:CC:DD:EE:FF")
    c._on_frames(None, frame(0x15, bytes(75)))
    assert c.station_firmware is None and c.probe_firmware == [None] * 4
    assert c.firmware_decode_status == "unrecognized_layout"
