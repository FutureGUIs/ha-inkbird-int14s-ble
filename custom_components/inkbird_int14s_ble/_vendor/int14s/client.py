"""Persistent authenticated INT-14S-BW session, independent of Home Assistant.

Discovery and retry scheduling belong to the caller. Each async_session uses
one fresh connection for both notifications and serialized commands.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from time import monotonic, time

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .auth import build_challenge_request, build_clock_sync, build_verify_response
from .const import CHR_BATTERY, CHR_FF01, CHR_FF02, CHR_FF03
from .protocol import (
    battery_payload,
    firmware_versions,
    food_high_frames,
    frame,
    snapshot_frames,
    target_report,
    temperature_payload,
)

_LOGGER = logging.getLogger(__name__)


class InkbirdConnectionError(Exception):
    """Station authentication, connection, or command failure."""


class INT14SBWClient:
    """Own protocol state and a single station connection.

    Supply a freshly discovered BLEDevice to async_session after each loss.
    Subclasses may customize error_type and the temperature/docking hooks.
    """

    error_type = InkbirdConnectionError

    def __init__(self, address):
        self.address = address.upper()
        self.food = [[None] * 4 for _ in range(4)]
        self.ambient = [None] * 4
        self.station_temperature = None
        self.batteries = [None] * 5
        self.probe_charging = [None] * 4
        self.base_charging = None
        self._last_state = 0
        self._probe_state_times = [0] * 4
        self._base_state_time = 0
        self.last_state_hex = None
        self.state_layout = "unknown"
        self.authentication_status = "not_started"
        self._verification_sent = False
        self._auth_rejected = False
        self._telemetry_event = asyncio.Event()
        self.last_state_length = None
        self.targets = [None] * 4
        self.brightness = None
        self.temperature_unit = None
        self.unit_write_status = "not_tested"
        self._unit_event = asyncio.Event()
        self._unit_sequence = 0
        self.device_info_payload_hex = None
        self.device_info_payload_length = None
        self.station_firmware = None
        self.probe_firmware = [None] * 4
        self.firmware_decode_status = "waiting_for_device_info"
        self._device_info_requests = 0
        self._device_info_received = False
        self.brightness_write_status = "not_tested"
        self._brightness_event = asyncio.Event()
        self._brightness_sequence = 0
        self.target_sources = ["unknown"] * 4
        self.write_status = ["not_tested"] * 4
        self.write_frames = [None] * 4
        self.reported_targets = [None] * 4
        self.report_sequences = [0] * 4
        self._target_events = [asyncio.Event() for _ in range(4)]
        self.available = False
        self.connection_stage = "not_started"
        self.last_error = None
        self.last_error_type = None
        self.last_failure_stage = None
        self.last_temperature_length = None
        self.last_battery_length = None
        self._last_temperature = 0
        self._last_rx = 0
        self._last_battery = 0
        self.connection_attempts = 0
        self.connection_started_monotonic = None
        self._connecting_client = None
        self.connect_cleanup_attempts = 0
        self.connect_cleanup_error = None
        self.successful_connections = 0
        self.poll_failures = 0
        self.invalid_temperature_packets = 0
        self.connection_events = deque(maxlen=10)
        self._disconnected = asyncio.Event()
        self._retry_event = asyncio.Event()
        self._unwatch_discovery = None
        self.discovery_wakeups = 0
        self._client = None
        self._task = None
        self._stop = asyncio.Event()
        self._auth = asyncio.Event()
        self._challenge_event = asyncio.Event()
        self._challenge = None
        self._frames_buffer = bytearray()
        self._write_lock = asyncio.Lock()
        self._listeners = []
        self._session_running = False

    def async_add_listener(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self):
        for listener in list(self._listeners):
            listener()

    def _record_event(self, reason):
        self.connection_events.append({"timestamp": time(), "reason": reason})

    def _on_disconnect(self, client):
        if client is self._client:
            self._disconnected.set()
            self.available = False
            self._auth.clear()
            self._notify()

    async def _connect(self, device):
        """Track a fresh client so failed/cancelled connects are cleaned up."""

        def create_client(*args, **kwargs):
            client = BleakClientWithServiceCache(*args, **kwargs)
            self._connecting_client = client
            return client

        self.connect_cleanup_error = None
        try:
            async with asyncio.timeout(35):
                return await establish_connection(
                    create_client,
                    device,
                    "INKBIRD INT-14S Bluetooth",
                    max_attempts=1,
                    disconnected_callback=self._on_disconnect,
                )
        except BaseException:
            # Includes cancellation during HA unload. The backend may still
            # hold a proxy connection even when is_connected is False.
            client = self._connecting_client
            if client is not None:
                self.connect_cleanup_attempts += 1
                try:
                    async with asyncio.timeout(10):
                        await client.disconnect()
                except Exception as exc:  # noqa: BLE001 - backend cleanup isolation
                    self.connect_cleanup_error = type(exc).__name__
            raise
        finally:
            self._connecting_client = None

    async def _write(self, payload):
        client = self._client
        if not client or not client.is_connected:
            raise self.error_type("The Bluetooth station is disconnected")
        characteristic = client.services.get_characteristic(CHR_FF02)
        response = bool(characteristic and "write" in characteristic.properties)
        async with asyncio.timeout(10):
            await client.write_gatt_char(CHR_FF02, payload, response=response)

    async def _snapshot(self):
        async with self._write_lock:
            for payload in snapshot_frames():
                await self._write(payload)
                await asyncio.sleep(0.1)
            if not self._device_info_received and self._device_info_requests < 3:
                self._device_info_requests += 1
                try:
                    await self._write(frame(0x15))
                except Exception as exc:  # noqa: BLE001 - optional device-info request
                    _LOGGER.debug("Device-info request failed: %s", type(exc).__name__)
        for uuid, callback in [
            (CHR_FF01, self._on_temperature),
            (CHR_BATTERY, self._on_battery),
            (CHR_FF03, self._on_state),
        ]:
            try:
                async with asyncio.timeout(10):
                    raw = await self._client.read_gatt_char(uuid)
                callback(uuid, raw)
            except Exception as exc:  # noqa: BLE001 - BLE backend failures need reconnect/read isolation
                _LOGGER.debug("Optional Bluetooth read skipped: %s", type(exc).__name__)

    async def _session(self, device):
        self._auth.clear()
        self._challenge_event.clear()
        self._challenge = None
        self._frames_buffer.clear()
        self._last_state = 0
        self._probe_state_times = [0] * 4
        self._base_state_time = 0
        self._verification_sent = False
        self._auth_rejected = False
        self._telemetry_event.clear()
        self.authentication_status = "pending"
        self._device_info_requests = 0
        self._device_info_received = False
        self.temperature_unit = None
        # Keep the last sample for diagnostics; entities remain unavailable
        # until authentication, and temperature freshness still expires at 90s.
        self._disconnected.clear()
        self.connection_stage = "connecting"
        self.connection_started_monotonic = monotonic()
        self.connection_attempts += 1
        client = await self._connect(device)
        self._client = client
        try:
            self.connection_stage = "subscribing"
            async with asyncio.timeout(20):
                await client.start_notify(CHR_FF02, self._on_frames)
                await client.start_notify(CHR_FF01, self._on_temperature)
            for uuid, callback in [
                (CHR_BATTERY, self._on_battery),
                (CHR_FF03, self._on_state),
            ]:
                try:
                    async with asyncio.timeout(10):
                        await client.start_notify(uuid, callback)
                except Exception as exc:  # noqa: BLE001 - BLE backend failures need reconnect/read isolation
                    _LOGGER.debug(
                        "Optional notification skipped: %s", type(exc).__name__
                    )
            self.connection_stage = "waiting_for_auth_challenge"
            await self._write(build_challenge_request())
            try:
                await asyncio.wait_for(self._challenge_event.wait(), 8)
            except TimeoutError as exc:
                raise self.error_type(
                    "No Bluetooth authentication challenge received"
                ) from exc
            self.connection_stage = "waiting_for_auth_ack"
            self._verification_sent = True
            self._telemetry_event.clear()
            await self._write(build_verify_response(self._challenge))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._auth.wait(), 5)
            if self._auth_rejected:
                raise self.error_type("Bluetooth authentication rejected")
            await self._write(build_clock_sync())
            if not self._auth.is_set():
                # Some firmware misses the ACK but still streams after verify.
                # Try reads; live data enables sensors, never write controls.
                self.connection_stage = "checking_stream_without_ack"
                await self._snapshot()
                try:
                    await asyncio.wait_for(self._telemetry_event.wait(), 8)
                except TimeoutError as exc:
                    raise self.error_type(
                        "No auth ACK or valid Bluetooth telemetry received"
                    ) from exc
            if self._auth_rejected:
                raise self.error_type("Bluetooth authentication rejected")
            self.available = True
            self.connection_stage = (
                "connected_authenticated"
                if self._auth.is_set()
                else "connected_unconfirmed"
            )
            if not self._auth.is_set():
                self.authentication_status = "streaming_without_ack_read_only"
            self.last_error = None
            self.last_error_type = None
            self.last_failure_stage = None
            self.successful_connections += 1
            self._record_event(self.authentication_status)
            self._last_rx = time()
            self._notify()
            failures = 0
            while client.is_connected and not self._stop.is_set():
                if self._auth_rejected:
                    raise self.error_type("Bluetooth authentication rejected")
                try:
                    await self._snapshot()
                    failures = 0
                except Exception as exc:
                    failures += 1
                    self.poll_failures += 1
                    if not client.is_connected or failures >= 3:
                        raise
                    _LOGGER.debug(
                        "Snapshot failed (%s/3): %s", failures, type(exc).__name__
                    )
                if time() - self._last_rx > 90:
                    raise self.error_type("No Bluetooth data received for 90 seconds")
                self._notify()
                if self._stop.is_set():
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._disconnected.wait(), 10)
                if self._disconnected.is_set():
                    raise self.error_type("Bluetooth station disconnected")
            if not client.is_connected and not self._stop.is_set():
                raise self.error_type("Bluetooth station disconnected")
        finally:
            self.available = False
            self._auth.clear()
            self._verification_sent = False
            self._client = None
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), 5)

    def _on_temperature(self, sender, data):
        self._last_rx = time()
        self.last_temperature_length = len(data)
        try:
            self.food, self.ambient, self.station_temperature = temperature_payload(
                bytes(data)
            )
        except ValueError as exc:
            self.last_error = str(exc)
            self.invalid_temperature_packets += 1
            self._notify()
            return
        self._last_temperature = time()
        if self._verification_sent:
            self._telemetry_event.set()
        self._mask_charging_probes()
        self._temperature_updated()
        self._notify()

    def _on_battery(self, sender, data):
        self._last_rx = time()
        self.last_battery_length = len(data)
        try:
            self.batteries = battery_payload(bytes(data))
            self._last_battery = time()
        except ValueError as exc:
            self.last_error = str(exc)
        self._notify()

    def _on_state(self, sender, data):
        # Compact INT-14S status: four two-byte probe blocks and three
        # global bytes. Probe charging is bit 1; base charging is byte 8 bit 0.
        self._last_rx = time()
        self.last_state_length = len(data)
        self.last_state_hex = bytes(data[:64]).hex()
        if not (1 <= len(data) <= 11 or len(data) == 15):
            self.last_error = (
                f"Expected compact BLE state or 15-byte INT-14S state, got {len(data)}"
            )
            return
        extended = len(data) == 15
        stride = 3 if extended else 2
        self.state_layout = (
            "int14s_three_byte_probe_blocks"
            if extended
            else "compact_two_byte_probe_blocks"
        )
        self._last_state = time()
        for probe in range(4):
            if probe * stride < len(data):
                self.probe_charging[probe] = bool(data[probe * stride] & 2)
                self._probe_state_times[probe] = self._last_state
        if extended:
            # Owner's USB on/off captures: global byte 12 is 0x53/0x52.
            # Bit 0 reports base charging; auth bits remain unvalidated.
            self.base_charging = bool(data[12] & 1)
            self._base_state_time = self._last_state
        elif len(data) >= 9:
            self.base_charging = bool(data[8] & 1)
            self._base_state_time = self._last_state
        if self._verification_sent:
            self._telemetry_event.set()
            if (
                not extended
                and len(data) >= 10
                and data[9] & 1
                and not self._auth_rejected
            ):
                self._confirm_auth("confirmed_by_state")
        if (
            self.last_error
            and self.last_error.startswith("Expected")
            and "state" in self.last_error
        ):
            self.last_error = None
        self._mask_charging_probes()
        self._notify()

    def _mask_charging_probes(self):
        for probe, charging in enumerate(self.probe_charging):
            if charging and time() - self._probe_state_times[probe] <= 90:
                self.food[probe] = [None] * 4
                self.ambient[probe] = None
                self._probe_docked(probe)

    def _confirm_auth(self, source):
        if self._auth_rejected:
            return
        self._auth.set()
        self.authentication_status = source
        if self.available:
            self.connection_stage = "connected_authenticated"
        self._notify()

    def _on_frames(self, sender, data):
        self._last_rx = time()
        self._frames_buffer.extend(data)
        while self._frames_buffer:
            length = self._frames_buffer[0]
            if length < 1:
                self._frames_buffer.clear()
                self.last_error = "Invalid Bluetooth control frame length"
                break
            if len(self._frames_buffer) < length + 1:
                break
            opcode = self._frames_buffer[1]
            payload = bytes(self._frames_buffer[2 : length + 1])
            del self._frames_buffer[: length + 1]
            if opcode == 0xFB and len(payload) == 6:
                self._challenge = payload
                self._challenge_event.set()
            elif opcode == 0xFC and payload:
                if payload[0] == 0:
                    self._confirm_auth("confirmed_by_ack")
                else:
                    self._auth_rejected = True
                    self._auth.clear()
                    self.available = False
                    self.authentication_status = "rejected"
                    self.last_error = "Bluetooth authentication rejected"
                    self._notify()
            elif opcode == 0x02 and (report := target_report(payload)):
                probe, target = report
                self.reported_targets[probe] = target
                self.report_sequences[probe] += 1
                self._target_events[probe].set()
                self.targets[probe] = target
                self.target_sources[probe] = "device_report"
                self._notify()
            elif opcode == 0x03 and len(payload) == 5:
                self._on_battery(sender, payload)
            elif opcode == 0x06 and len(payload) == 1 and payload[0] <= 100:
                self.brightness = payload[0]
                self._brightness_sequence += 1
                self._brightness_event.set()
                self._notify()
            elif opcode == 0x04 and payload in (b"C", b"F"):
                self.temperature_unit = payload.decode("ascii")
                self._unit_sequence += 1
                self._unit_event.set()
                self._notify()
            elif opcode == 0x15 and payload:
                # Keep the response for validating this model's version layout.
                # Do not guess a firmware version from bytes containing IDs.
                self.device_info_payload_hex = payload.hex()
                self.device_info_payload_length = len(payload)
                self._device_info_received = True
                versions = firmware_versions(payload)
                if versions:
                    self.station_firmware = versions[0]
                    self.probe_firmware = versions[1:]
                    self.firmware_decode_status = "decoded_int14s_75_byte_layout"
                else:
                    self.firmware_decode_status = "unrecognized_layout"
                self._notify()

    async def write_food_high(self, probe, value):
        frames = food_high_frames(probe, value)
        if not self.available or not self._auth.is_set():
            raise self.error_type(
                "Wait for an authenticated Bluetooth connection before writing"
            )
        async with self._write_lock:
            event = self._target_events[probe]
            event.clear()
            sequence = self.report_sequences[probe]
            self.write_frames[probe] = [payload.hex() for payload in frames]
            self.write_status[probe] = "sending"
            try:
                for payload in frames:
                    await self._write(payload)
                    await asyncio.sleep(0.15)
                self.targets[probe] = value
                self.target_sources[probe] = "last_requested"
                self.write_status[probe] = "sent_awaiting_readback"
                self._notify()
                await asyncio.sleep(0.5)
                await self._write(frame(0x02, bytes([1 << probe])))
                if self.report_sequences[probe] == sequence:
                    try:
                        await asyncio.wait_for(event.wait(), 3)
                    except TimeoutError:
                        pass
                if self.report_sequences[probe] > sequence:
                    actual = self.reported_targets[probe]
                    self.targets[probe] = actual
                    self.target_sources[probe] = "device_report"
                    self.write_status[probe] = (
                        "confirmed_by_readback"
                        if actual
                        == (round(value * 10) / 10 if value is not None else None)
                        else "readback_mismatch"
                    )
            except Exception as exc:
                self.write_status[probe] = "write_failed"
                self.last_error = type(exc).__name__
                raise self.error_type(
                    "Bluetooth target write failed; check diagnostics"
                ) from exc
            finally:
                self._notify()

    def _require_auth(self):
        if not self.available or not self._auth.is_set():
            raise self.error_type(
                "Wait for an authenticated Bluetooth connection before writing"
            )

    async def write_brightness(self, value):
        if (
            type(value) not in (int, float)
            or not 0 <= value <= 100
            or value != int(value)
        ):
            raise self.error_type("Brightness must be a whole percentage from 0 to 100")
        self._require_auth()
        async with self._write_lock:
            sequence = self._brightness_sequence
            self._brightness_event.clear()
            try:
                await self._write(frame(0x05, bytes([int(value)])))
                self.brightness = int(value)
                self.brightness_write_status = "sent_awaiting_readback"
                self._notify()
                await asyncio.sleep(0.5)
                await self._write(frame(0x06))
                if self._brightness_sequence == sequence:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._brightness_event.wait(), 3)
                if self._brightness_sequence > sequence:
                    self.brightness_write_status = (
                        "confirmed_by_readback"
                        if self.brightness == value
                        else "readback_mismatch"
                    )
            except Exception as exc:
                self.brightness_write_status = "write_failed"
                raise self.error_type("Bluetooth brightness write failed") from exc
            finally:
                self._notify()

    async def acknowledge_alarm(self):
        self._require_auth()
        async with self._write_lock:
            try:
                # Acknowledge active temperature alarms; target settings remain.
                await self._write(frame(0x0D, b"\x0f"))
            except Exception as exc:
                raise self.error_type("Bluetooth alarm acknowledgement failed") from exc

    async def write_temperature_unit(self, unit):
        if unit not in ("C", "F"):
            raise self.error_type("Temperature unit must be C or F")
        self._require_auth()
        async with self._write_lock:
            sequence = self._unit_sequence
            self._unit_event.clear()
            self.unit_write_status = "sending"
            try:
                await self._write(frame(0x03, unit.encode("ascii")))
                self.temperature_unit = unit
                self.unit_write_status = "sent_awaiting_readback"
                self._notify()
                await asyncio.sleep(0.5)
                await self._write(frame(0x04))
                if self._unit_sequence == sequence:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._unit_event.wait(), 3)
                if self._unit_sequence > sequence:
                    self.unit_write_status = (
                        "confirmed_by_readback"
                        if self.temperature_unit == unit
                        else "readback_mismatch"
                    )
            except Exception as exc:
                self.unit_write_status = "write_failed"
                raise self.error_type(
                    "Bluetooth temperature unit write failed"
                ) from exc
            finally:
                self._notify()

    def _temperature_updated(self):
        """Hook for caller-owned temperature trends."""

    def _probe_docked(self, probe):
        """Hook for clearing caller-owned trends when a probe is docked."""

    async def async_session(self, device):
        """Run until disconnection; always release the client on exit.

        On failure, rediscover the device before calling again. Cancellation
        also cleans up a pending proxy connection.
        """
        if self._session_running:
            raise self.error_type("A station session is already running")
        self._session_running = True
        self._stop.clear()
        try:
            await self._session(device)
        finally:
            self._session_running = False
            self.available = False
            self._auth.clear()
            self._notify()

    def stop(self):
        """Request that the active session stop."""
        self._stop.set()
        self._disconnected.set()
