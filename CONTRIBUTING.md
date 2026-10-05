# Contributing

The HA adapter is in `custom_components/inkbird_int14s_ble`. Station protocol
and session code live in its bundled `_vendor/int14s` package; keep its source
provenance and hashes current when changing it. Do not introduce a second
connection for commands or change working polling intervals without evidence.

## Tests

Use Python 3.14. Create an isolated environment and install
`requirements-test.txt`, then run from the repository root:

```sh
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  -p pytest_mock -p pytest_asyncio.plugin -p no:cacheprovider tests -q
ruff check --select E,F,I custom_components
ruff format --check custom_components
python scripts/validate_package.py
```

The Windows test boundary replaces HA's Linux-only Bluetooth host adapter.
Entities, registries and Home Assistant classes are tested against real HA
modules. Simulated tests do not substitute for checking startup and power-cycle
recovery on the station and proxy hardware. Changes to packet layouts should
include anonymized capture vectors.

GitHub Actions validates HACS metadata, runs Home Assistant's hassfest checks,
and runs tests and packaging checks. This repository is a HACS custom repository;
submission to the default catalog is a separate step.
