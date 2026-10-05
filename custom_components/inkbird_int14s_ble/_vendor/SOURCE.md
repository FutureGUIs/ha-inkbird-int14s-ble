# Library source

The `int14s` package is a bundled snapshot developed in our
[inkbird-ble fork](https://github.com/FutureGUIs/inkbird-ble), based on upstream
1.7.1 at `c88a839d2275ea8a773b61b50f028bb23baeec37`. Its source is published
with this integration; the INT-14S-BW additions are not yet released separately
by the library fork or accepted upstream.

Bundling this subpackage avoids overriding HA's official Inkbird dependency.
It imports no Home Assistant modules and owns one authenticated session for
readings and serialized controls. Discovery/retry scheduling and entities remain
in the HA adapter. The upstream MIT license and additional notices are retained.
File hashes are recorded in `source.json`.
