"""Bluetooth diagnostics with station addresses omitted."""

import re
from time import monotonic, time

from homeassistant.components import bluetooth

from .registry import registration_diagnostics


def connection_reachability(hass, address):
    """Use HA's connection-path/slot report without exposing addresses."""
    try:
        report = bluetooth.async_address_reachability_diagnostics(
            hass, address, bluetooth.BluetoothReachabilityIntent.CONNECTION
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must survive unavailable backend
        return f"Reachability report unavailable: {type(exc).__name__}"
    report = re.sub(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", "[address]", report)
    return re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", report)


async def async_get_config_entry_diagnostics(hass, entry):
    c = entry.runtime_data
    return {
        "version": "0.2.1",
        "transport_library": "FutureGUIs/inkbird-ble (bundled int14s client)",
        "transport_module": type(c).__mro__[1].__module__,
        "connect_cleanup_attempts": c.connect_cleanup_attempts,
        "connect_cleanup_error": c.connect_cleanup_error,
        "connection_reachability": connection_reachability(hass, c.address),
        "seconds_in_connection_attempt": round(
            monotonic() - c.connection_started_monotonic, 1
        )
        if c.connection_stage == "connecting"
        and c.connection_started_monotonic is not None
        else None,
        "discovery_wakeups": c.discovery_wakeups,
        "temperature_unit": c.temperature_unit,
        "unit_write_status": c.unit_write_status,
        "device_info_requests": c._device_info_requests,
        "device_info_received_this_session": c._device_info_received,
        "device_info_payload_length": c.device_info_payload_length,
        "device_info_payload_hex": None
        if c.firmware_decode_status == "decoded_int14s_75_byte_layout"
        else c.device_info_payload_hex,
        "firmware_decode_status": c.firmware_decode_status,
        "station_firmware": c.station_firmware,
        "probe_firmware": c.probe_firmware,
        "state_layout": c.state_layout,
        "authentication_status": c.authentication_status,
        "connected_reading": c.available,
        "state_packet_hex": c.last_state_hex,
        "probe_charging": c.probe_charging,
        "base_charging": c.base_charging,
        "state_packet_length": c.last_state_length,
        "seconds_since_valid_state": round(time() - c._last_state, 1)
        if c._last_state
        else None,
        "connectable_scanner_count": bluetooth.async_scanner_count(
            hass, connectable=True
        ),
        "station_seen_connectable": bluetooth.async_ble_device_from_address(
            hass, c.address, connectable=True
        )
        is not None,
        "connection_session_attempts": c.connection_attempts,
        "successful_connections": c.successful_connections,
        "poll_failures": c.poll_failures,
        "invalid_temperature_packets": c.invalid_temperature_packets,
        "recent_connection_events": list(c.connection_events),
        "seconds_since_bluetooth_data": round(time() - c._last_rx, 1)
        if c._last_rx
        else None,
        "seconds_since_valid_temperature": round(time() - c._last_temperature, 1)
        if c._last_temperature
        else None,
        "seconds_since_valid_battery": round(time() - c._last_battery, 1)
        if c._last_battery
        else None,
        "brightness": c.brightness,
        "brightness_write_status": c.brightness_write_status,
        "entity_registration": registration_diagnostics(hass, entry),
        "connection_stage": c.connection_stage,
        "connection_task_running": bool(c._task and not c._task.done()),
        "connection_task_error": (
            type(c._task.exception()).__name__
            if c._task
            and c._task.done()
            and not c._task.cancelled()
            and c._task.exception() is not None
            else None
        ),
        "connected_authenticated": c.available and c._auth.is_set(),
        "last_error": c.last_error,
        "last_error_type": c.last_error_type,
        "last_failure_stage": c.last_failure_stage,
        "temperature_packet_length": c.last_temperature_length,
        "battery_packet_length": c.last_battery_length,
        "food_fahrenheit": c.food,
        "ambient_fahrenheit": c.ambient,
        "station_fahrenheit": c.station_temperature,
        "batteries": c.batteries,
        "targets_fahrenheit": c.targets,
        "target_sources": c.target_sources,
        "reported_targets_fahrenheit": c.reported_targets,
        "write_status": c.write_status,
        "last_target_frames": c.write_frames,
    }
