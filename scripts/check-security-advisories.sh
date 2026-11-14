#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path
import re
import tomllib

packages = tomllib.loads(Path("Cargo.lock").read_text())["package"]
zip_versions = {package["version"] for package in packages if package["name"] == "zip"}
if not zip_versions:
    raise SystemExit("ZIP security check needs reassessment: dependency missing")
for version in zip_versions:
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", version)
    if not match or tuple(map(int, match.groups())) < (9, 0, 5):
        raise SystemExit(f"ZIP {version} is not a patched stable release for GHSA-m665-v7pm-7grj. Require 9.0.5 or newer")
for package in packages:
    if package["name"] != "rsa":
        continue
    version = package["version"]
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", version)
    if not match or tuple(map(int, match.groups())) < (0, 10, 0):
        raise SystemExit(f"RSA {version} is not a patched stable release for RUSTSEC-2023-0071. Require 0.10.0 or newer")
PY

echo "ZIP and RSA dependency guards passed. No RustSec vulnerability exceptions are applied."
if [[ "${1:-}" == "--policy-only" ]]; then
  [[ "$#" == 1 ]] || { echo "--policy-only takes no other arguments" >&2; exit 1; }
  exit 0
fi
exec cargo audit "$@"
