"""Home Assistant discovery, entity updates, and ETA for the library client."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from time import time

from homeassistant.components import bluetooth
from homeassistant.core import callback as ha_callback
from homeassistant.exceptions import HomeAssistantError

from ._vendor.int14s import INT14SBWClient
from .trend import TemperatureTrend

_LOGGER = logging.getLogger(__name__)


class InkbirdCoordinator(INT14SBWClient):
    error_type = HomeAssistantError

    def __init__(self, hass, address):
        super().__init__(address)
        self.hass = hass
        self.trends = [TemperatureTrend() for _ in range(4)]

    def _temperature_updated(self):
        for index, trend in enumerate(self.trends):
            trend.add(self._last_temperature, self.food[index][0])

    def _probe_docked(self, probe):
        self.trends[probe].samples.clear()

    async def async_start(self):
        self._stop.clear()
        self.connection_stage = "starting"
        if self._unwatch_discovery is None:
            self._unwatch_discovery = bluetooth.async_register_callback(
                self.hass,
                self._on_advertisement,
                {"address": self.address, "connectable": True},
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        self._task = self.hass.async_create_background_task(
            self._run(), "inkbird-int14s-ble"
        )

    async def async_stop(self):
        self._stop.set()
        self._retry_event.set()
        if self._unwatch_discovery:
            self._unwatch_discovery()
            self._unwatch_discovery = None
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.available = False
        self.connection_stage = "stopped"
        self._notify()

    @ha_callback
    def _on_advertisement(self, service_info, change):
        if self.connection_stage in (
            "starting",
            "waiting_for_station",
            "waiting_for_adapter",
        ):
            self.discovery_wakeups += 1
            self._retry_event.set()

    async def _run(self):
        while not self._stop.is_set():
            self._retry_event.clear()
            try:
                if not bluetooth.async_scanner_count(self.hass, connectable=True):
                    self.connection_stage = "waiting_for_adapter"
                    self.last_error = (
                        "No connectable Bluetooth adapter or proxy is available"
                    )
                else:
                    device = bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    )
                    if device:
                        await self.async_session(device)
                    else:
                        self.connection_stage = "waiting_for_station"
                        self.last_error = (
                            "Station not currently seen by a connectable "
                            "Bluetooth adapter/proxy"
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - BLE backend failures need reconnect/read isolation
                self.last_failure_stage = self.connection_stage
                self.last_error_type = type(exc).__name__
                self.connection_stage = "retrying"
                self.last_error = re.sub(
                    r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}",
                    "[address]",
                    str(exc) or self.last_error_type,
                )
                self.last_error = re.sub(
                    r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", self.last_error
                )[:1000]
                _LOGGER.warning(
                    "Bluetooth session ended at %s (%s): %s",
                    self.last_failure_stage,
                    self.last_error_type,
                    self.last_error,
                )
                self._record_event(self.last_error)
            finally:
                self.available = False
                self._auth.clear()
                for trend in self.trends:
                    trend.samples.clear()
                self._notify()
            if self._stop.is_set():
                break
            try:
                # Failed connects need quiet time for proxies to release their
                # pending links and resume scanning; advertisements must not
                # shorten this cooldown.
                waiter = (
                    self._stop.wait()
                    if self.connection_stage == "retrying"
                    else self._retry_event.wait()
                )
                await asyncio.wait_for(waiter, 10)
            except TimeoutError:
                pass

    def eta(self, probe):
        return self.trends[probe].minutes_to_target(self.targets[probe], time())
