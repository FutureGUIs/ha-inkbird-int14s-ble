"""Check the install layout, HACS metadata, translations and library hashes."""

import ast
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
components = [p for p in (root / "custom_components").iterdir() if p.is_dir()]
assert len(components) == 1, "HACS must contain exactly one integration"
component = components[0]
manifest = json.loads((component / "manifest.json").read_text())
for key in ("domain", "documentation", "issue_tracker", "codeowners", "name", "version"):
    assert manifest.get(key), f"Missing HACS manifest field: {key}"
assert manifest["domain"] == component.name
assert manifest["documentation"].endswith("FutureGUIs/ha-inkbird-int14s-ble")
assert manifest["codeowners"] == ["@FutureGUIs"]
hacs = json.loads((root / "hacs.json").read_text())
assert hacs["name"] == manifest["name"]
assert not hacs.get("content_in_root", False)
assert not hacs.get("zip_release", False)
assert (component / "brand/icon.png").is_file()
assert (component / "LICENSE").is_file()
assert (component / "_vendor/LICENSE").is_file()
assert (root / "LICENSE").is_file()
assert (root / "README.md").is_file()
strings = json.loads((component / "strings.json").read_text())
assert strings == json.loads((component / "translations/en.json").read_text())
for file in component.rglob("*.json"):
    json.loads(file.read_text())
for file in component.rglob("*.py"):
    ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
source = json.loads((component / "_vendor/source.json").read_text())
for filename, expected in source["sha256"].items():
    data = (component / "_vendor/int14s" / filename).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected, f"Library snapshot mismatch: {filename}"
for pattern in ("*.log", ".env"):
    assert not list(component.rglob(pattern)), f"Unexpected packaged artifact: {pattern}"
print(f"HACS package checks passed: {manifest['domain']} {manifest['version']}")
