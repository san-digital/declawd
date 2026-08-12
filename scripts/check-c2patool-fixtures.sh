#!/usr/bin/env bash
set -euo pipefail

manifest=fixtures/c2pa/signed-fixture-manifest.json
if [[ ! -f "$manifest" ]]; then
  echo "signed fixture manifest absent" >&2
  exit 1
fi

declawd_bin=${DECLAWD_BIN:-target/debug/declawd}
if [[ ! -x "$declawd_bin" ]]; then
  echo "Declawd binary not found or not executable: $declawd_bin" >&2
  exit 1
fi

python3 - "$manifest" "$declawd_bin" <<'PY'
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
declawd = sys.argv[2]
if manifest.get("schema") != "declawd.c2pa-fixtures/v1":
    raise SystemExit("unexpected C2PA fixture manifest schema")
version = subprocess.run(
    ["c2patool", "--version"], capture_output=True, text=True, check=True
).stdout.strip()
expected_version = manifest["oracle"]["version"]
if version != f"c2patool {expected_version}":
    raise SystemExit(f"expected c2patool {expected_version}, got {version!r}")

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

for case in manifest["cases"]:
    signed = Path(case["path"])
    source = Path(case["source_path"])
    if sha256(signed) != case["sha256"]:
        raise SystemExit(f"{signed}: signed fixture hash mismatch")
    if sha256(source) != case["source_sha256"]:
        raise SystemExit(f"{source}: source fixture hash mismatch")

    result = subprocess.run(["c2patool", str(signed)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{signed}: c2patool failed: {result.stderr.strip()}")
    report = json.loads(result.stdout)
    active_label = report.get("active_manifest")
    if not active_label or active_label not in report.get("manifests", {}):
        raise SystemExit(f"{signed}: independent oracle found no active embedded manifest")
    active = report.get("validation_results", {}).get("activeManifest", {})
    success = {item["code"] for item in active.get("success", [])}
    missing = set(case["required_binding_codes"]) - success
    if missing:
        raise SystemExit(f"{signed}: missing hard-binding codes {sorted(missing)}")

    with tempfile.TemporaryDirectory(prefix="declawd-c2pa-oracle-") as directory:
        cleaned = Path(directory) / source.name
        clean = subprocess.run(
            [declawd, "clean", "c2pa", str(signed), "--output", str(cleaned), "--json"],
            capture_output=True,
            text=True,
        )
        if clean.returncode != 0:
            raise SystemExit(f"{signed}: Declawd clean failed: {clean.stderr.strip()}")
        clean_report = json.loads(clean.stdout)
        verification = clean_report.get("verification", {})
        required_true = (
            "embedded_c2pa_absent",
            "non_c2pa_bytes_unchanged",
            "compressed_image_data_unchanged",
        )
        if any(verification.get(name) is not True for name in required_true):
            raise SystemExit(f"{signed}: incomplete Declawd verification report")
        if sha256(cleaned) != case["source_sha256"]:
            raise SystemExit(f"{signed}: cleaned bytes do not match the source fixture")
        absent = subprocess.run(
            ["c2patool", str(cleaned)], capture_output=True, text=True
        )
        if absent.returncode == 0 or "No claim found" not in absent.stderr:
            raise SystemExit(f"{signed}: independent oracle still found a claim")

print(f"verified {len(manifest['cases'])} test-signed C2PA fixtures end to end")
PY
