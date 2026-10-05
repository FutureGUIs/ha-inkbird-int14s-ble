"""INT-14S-BW BLE layouts adapted from zampix1's MIT protocol implementation."""

import math
import re

SENTINELS = {32766, 32767, 32768}


def firmware_versions(payload):
    """Decode the owner's captured 75-byte INT-14S device-info layout.

    Five six-byte ASCII versions start at 10, then every 13 bytes.
    Reject other layouts rather than interpret address bytes as versions.
    """
    if len(payload) != 75:
        return None
    versions = [payload[offset : offset + 6] for offset in (10, 23, 36, 49, 62)]
    if not all(re.fullmatch(rb"V[0-9]\.[0-9]\.[0-9]", version) for version in versions):
        return None
    return [version.decode("ascii") for version in versions]


def frame(opcode, payload=b""):
    return bytes([len(payload) + 1, opcode]) + payload


def food_high_frames(probe, target_f):
    """Food target plus pre-alarm reset; Fahrenheit tenths, explicit probe mask."""
    if probe not in range(4):
        raise ValueError("Invalid probe")
    if target_f is not None and (
        type(target_f) not in (int, float)
        or not math.isfinite(target_f)
        or not 32 <= target_f <= 212
    ):
        raise ValueError("Food target must be 32–212 Fahrenheit")
    mask = 1 << probe
    payload = (
        bytes([mask, 0x10 if target_f is not None else 0])
        + (round(target_f * 10) if target_f is not None else 0).to_bytes(
            2, "little", signed=True
        )
        + bytes(4)
    )
    return [frame(0x01, payload), frame(0x23, bytes([mask, 0, 0, 0, 0]))]


def temperature_payload(raw):
    if len(raw) != 54:
        raise ValueError(f"Expected 54-byte BLE temperatures, got {len(raw)}")

    def temperature(offset, scale):
        value = int.from_bytes(raw[offset : offset + 2], "little", signed=True)
        return None if abs(value) in SENTINELS else value / scale

    food = [
        [temperature(probe * 13 + off, 100) for off in (2, 4, 6, 8)]
        for probe in range(4)
    ]
    ambient = [temperature(probe * 13 + 10, 10) for probe in range(4)]
    return food, ambient, temperature(52, 10)


def battery_payload(raw):
    if len(raw) != 5:
        raise ValueError(f"Expected five BLE battery bytes, got {len(raw)}")
    return [value if value <= 100 else None for value in raw]


def target_report(payload):
    if (
        len(payload) != 8
        or payload[0] not in (1, 2, 4, 8)
        or payload[1] not in (0, 1, 16, 17)
    ):
        return None
    probe = payload[0].bit_length() - 1
    target = (
        int.from_bytes(payload[2:4], "little", signed=True) / 10
        if payload[1] & 16
        else None
    )
    return probe, target


def snapshot_frames():
    # Reads only: current temperature/state/battery, food targets and brightness.
    return [
        bytes.fromhex("02f10102f10302f119"),
        *[frame(0x02, bytes([1 << p])) for p in range(4)],
        frame(0x06),
        frame(0x04),
    ]
