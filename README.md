# INKBIRD INT-14S Bluetooth

![INKBIRD](custom_components/inkbird_int14s_ble/brand/icon.png)

[![Validate](https://github.com/FutureGUIs/ha-inkbird-int14s-ble/actions/workflows/validate.yml/badge.svg)](https://github.com/FutureGUIs/ha-inkbird-int14s-ble/actions/workflows/validate.yml)

A Bluetooth-only Home Assistant integration for the **INT-14S-BW** station
and its four wireless probes. It provides readings and controls through a local
Bluetooth adapter or an ESPHome Bluetooth proxy. Setup needs no Inkbird account,
Tuya credentials, local key, Wi-Fi connection, or cloud service.

## Features

- Four food-temperature channels and one ambient-temperature channel per probe.
- Station temperature, station battery, and all four probe batteries.
- Charging/docking indicators for the station and each probe.
- Station and probe firmware versions.
- A food high target number and a separate clear-target button for each probe.
- Station brightness, alarm acknowledgment, and a Celsius/Fahrenheit selector.
- A Time to Temp estimate for each probe using its first food channel.
- Bluetooth discovery, automatic reconnection, and downloadable diagnostics.

All 51 entities are grouped under one device. Clearing a target sends a clear
command to the station; the integration does not keep it for later. Target
writes set the food high limit and clear food low and ambient limits.

## Requirements

- Home Assistant **2026.9.0 or later**.
- An **INT-14S-BW** station. The INT-14-BW and other Inkbird models use different
  layouts and are not supported by this integration.
- Home Assistant's Bluetooth integration and a connectable local adapter, or
  an ESPHome Bluetooth proxy with `bluetooth_proxy.active: true`.

The station must be in Bluetooth range. Close the Inkbird phone app and any
other integration actively connecting to the same station.

## Install with HACS

This repository can be installed as a HACS **custom repository**. It is not yet
listed in the default HACS catalog.

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=FutureGUIs&repository=ha-inkbird-int14s-ble&category=integration)

1. In HACS, open the three-dot menu and select **Custom repositories**.
2. Add `https://github.com/FutureGUIs/ha-inkbird-int14s-ble` with type **Integration**.
3. Find **INKBIRD INT-14S Bluetooth** in HACS and download it.
4. **Restart Home Assistant**.
5. Go to **Settings → Devices & services → Add integration** and choose
   **INKBIRD INT-14S Bluetooth**. You can also accept its Bluetooth discovery.
6. Select the station or enter its Bluetooth address. Wait for it to connect
   and authenticate; sensor creation does not require the station to be online.

### Updating an existing manual installation

Install through HACS and restart HA. Keep the existing integration entry;
the domain, unique IDs and entity names are preserved. There is no need to
remove the device or set it up again. Release **0.2.1** packages the working
0.2.0 connection code for HACS without changing its polling or commands.

### Manual installation

Copy the entire `custom_components/inkbird_int14s_ble` folder into HA's
`config/custom_components` directory, including `_vendor/` and `brand/`.
Restart Home Assistant and add the integration as described above.

## Controls and readings

`Probe 1 target` through `Probe 4 target` set the food high target. Use each
probe's **Clear target** button to remove its target on the device. The target
range is 32–212 °F. Write controls become available after authentication.

The Celsius/Fahrenheit selector changes the station's display setting. Sensor
display units in Home Assistant follow HA's temperature settings independently.
Docked probes may have no live cooking-temperature reading. Battery and
firmware values may arrive after the initial temperature readings.

Time to Temp uses a five-minute temperature trend and needs at least three
samples spanning one minute. It shows an estimate while the probe is heating
toward its target, and becomes unknown when a useful estimate cannot be made.
It is an estimate, not a timer or a guarantee of cooking completion.

## Connection troubleshooting

Place a connectable proxy near the station and ensure its active connections
are enabled. When the station is off, entities become unavailable; the
integration retries when it is rediscovered. The owner has observed fast
power-off detection and power-on reconnection with the 0.2.0 client, but timing
depends on the Bluetooth adapter/proxy and the station becoming ready.

If it does not recover, download diagnostics from the integration entry. For
a connection trace, enable debug logging, reproduce the issue, and download
the log. Include the HA version, proxy firmware and whether restarting the
station or reloading the integration changes the outcome in an
[issue](https://github.com/FutureGUIs/ha-inkbird-int14s-ble/issues).
Remove addresses and other identifying information before posting logs.

## Development and attribution

The station protocol is developed in our [inkbird-ble fork](https://github.com/FutureGUIs/inkbird-ble)
and bundled privately here to avoid replacing the library used by HA's official
Inkbird integration. It owns one authenticated Bluetooth session for both reads
and controls. Entity registration, discovery and Time to Temp stay in this
integration. This is a custom integration, not an official Inkbird or HA release.

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests and validation,
[CHANGELOG.md](CHANGELOG.md) for releases, and [ATTRIBUTION.md](ATTRIBUTION.md)
for protocol and brand-image sources. The code is MIT licensed; upstream
notices are retained in `LICENSES/` and the bundled library package.
