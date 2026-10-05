"""Windows unit tests replace only the host Bluetooth integration boundary.

HA's USB dependency requires Linux-only packages here. Entities, configuration
flow classes, protocol and coordinator code use real Home Assistant modules.
"""

import sys
import types
from unittest.mock import MagicMock

if sys.platform == "win32":
    from home_assistant_bluetooth import BluetoothServiceInfoBleak

    adapter = types.ModuleType("homeassistant.components.bluetooth")
    adapter.BluetoothServiceInfoBleak = BluetoothServiceInfoBleak
    adapter.async_ble_device_from_address = MagicMock()
    adapter.async_scanner_count = MagicMock(return_value=1)
    adapter.async_discovered_service_info = MagicMock(return_value=[])
    adapter.async_register_callback = MagicMock()
    adapter.BluetoothScanningMode = types.SimpleNamespace(ACTIVE="active")
    adapter.BluetoothReachabilityIntent = types.SimpleNamespace(CONNECTION="connection")
    adapter.async_address_reachability_diagnostics = MagicMock(
        return_value="No test backend"
    )
    sys.modules["homeassistant.components.bluetooth"] = adapter
