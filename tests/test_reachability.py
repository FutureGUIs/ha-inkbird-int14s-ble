"""Connection-path diagnostic reporting and redaction."""

from unittest.mock import MagicMock

from custom_components.inkbird_int14s_ble.diagnostics import connection_reachability


def test_reachability_preserves_slot_report_and_redacts_addresses(mocker):
    report = mocker.patch(
        "custom_components.inkbird_int14s_ble.diagnostics.bluetooth.async_address_reachability_diagnostics",
        return_value="Station AA:BB:CC:DD:EE:FF via 12:34:56:78:9A:BC (192.168.1.8), RSSI -55, slots 3/3 allocated",
    )
    value = connection_reachability(MagicMock(), "AA:BB:CC:DD:EE:FF")
    assert "RSSI -55, slots 3/3 allocated" in value
    assert "AA:BB" not in value and "12:34" not in value and "192.168" not in value
    assert value.count("[address]") == 2
    report.assert_called_once()


def test_reachability_backend_failure_does_not_break_diagnostics(mocker):
    mocker.patch(
        "custom_components.inkbird_int14s_ble.diagnostics.bluetooth.async_address_reachability_diagnostics",
        side_effect=RuntimeError,
    )
    assert (
        connection_reachability(MagicMock(), "AA:BB:CC:DD:EE:FF")
        == "Reachability report unavailable: RuntimeError"
    )
