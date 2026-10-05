# Changelog

## 0.2.1

- First public HACS release, with repository metadata, installation instructions,
  licensing, validation workflows and the bundled INT-14S-BW protocol client.
- Preserves the working 0.2.0 connection, polling and control behavior.

## 0.2.0

- Moved station authentication, packet decoding, Bluetooth-session ownership and
  serialized controls into an independent client developed in our inkbird-ble fork.
- Kept existing entity IDs and all readings, controls, charging and ETA features.
- Owner reports improved power-off detection and power-on reconnection.
