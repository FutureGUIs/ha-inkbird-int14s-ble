# Attribution

This independent integration incorporates work from these MIT-licensed projects:

- [boris327/ha-inkbird-int14bw](https://github.com/boris327/ha-inkbird-int14bw): Bluetooth connection, configuration, and authentication design; copyright 2026 Boris Pustilnik.
- [zampix1/ha-inkbird-int14](https://github.com/zampix1/ha-inkbird-int14): INT-14S temperature layout and BLE target frame builder; copyright 2026, as stated in its license.
- [Bluetooth-Devices/inkbird-ble](https://github.com/Bluetooth-Devices/inkbird-ble): the upstream library underlying our fork; copyright 2022 J. Nick Koston.
- [paul43210/inkbird-bw-ble](https://github.com/paul43210/inkbird-bw-ble): reverse-engineered authentication algorithm and protocol documentation; copyright 2026 Paul Faure.

Boris's and zampix1's complete notices are retained in `LICENSES/` and in the bundled library's `LICENSES/`. The upstream inkbird-ble notice and Paul Faure's complete notice are retained in `custom_components/inkbird_int14s_ble/_vendor/LICENSE`, so they are included when HACS installs the integration. Paul's notice is also reproduced below.

The rolling Time to Temp calculation was developed during this project. This is an independent custom integration, not an official release of Inkbird, Home Assistant, or the upstream projects.

## Paul Faure's MIT notice

Source: [paul43210/inkbird-bw-ble/LICENSE](https://github.com/paul43210/inkbird-bw-ble/blob/main/LICENSE).

MIT License

Copyright (c) 2026 Paul Faure

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## INKBIRD brand assets

`custom_components/inkbird_int14s_ble/brand/icon.png` and `icon@2x.png` are unchanged copies from [Home Assistant Brands](https://github.com/home-assistant/brands/tree/master/core_integrations/inkbird).

Source Git blob hashes: `ef321c3c0ecfed0318b982c9e237e90279c2a376` and `c3d63328d5aef0907e355b915533edf3cae9d6c1`, respectively.

INKBIRD trademarks and images belong to their respective owners and are included for identification; their use does not imply endorsement. The software's MIT license does not grant rights to these trademarks or brand images.
