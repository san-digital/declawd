#!/usr/bin/env bash
set -euo pipefail

# Reviewed on 29 October 2026. SECURITY.md records the affected operations, dependency constraints and source paths for these five exceptions.
exception_ids=(RUSTSEC-2023-0071 RUSTSEC-2026-0387 RUSTSEC-2026-0367 RUSTSEC-2026-0368 RUSTSEC-2026-0369)
exception_expires=2026-11-28
warn_days=14
audit_date=${DECLAWD_AUDIT_DATE:-$(date -u +%F)}

if [[ ! "$audit_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "invalid audit date: $audit_date" >&2
  exit 1
fi
if [[ "$audit_date" > "$exception_expires" ]]; then
  echo "advisory exceptions expired on $exception_expires; reassess the affected operations and dependencies" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import hashlib
import tomllib

expected = {"c2pa": "0.90.22", "rsa": "0.9.10", "crypto-bigint": "0.5.5", "zip": "8.6.0"}
packages = tomllib.loads(Path("Cargo.lock").read_text())["package"]
for name, version in expected.items():
    actual = {package["version"] for package in packages if package["name"] == name}
    if actual != {version}:
        raise SystemExit(f"advisory exception needs reassessment: {name} versions changed to {sorted(actual)}")

source_hash = hashlib.sha256()
for path in sorted(Path("src").rglob("*.rs")):
    source_hash.update(str(path).encode() + b"\0" + path.read_bytes() + b"\0")
if source_hash.hexdigest() != "606c1bf928fa7cd243eb99285149fe6f25eda4de56a191a223fe6e0407ce7f36":
    raise SystemExit("advisory exception needs reassessment: reviewed Rust source changed")
PY

# Both date implementations use midnight UTC so crossing a second cannot change the whole-day warning calculation.
midnight() {
  date -u -d "$1 00:00:00" +%s 2>/dev/null || date -u -j -f "%F %T" "$1 00:00:00" +%s
}
days_left=$(( ( $(midnight "$exception_expires") - $(midnight "$audit_date") ) / 86400 ))
if (( days_left <= warn_days )); then
  echo "::warning title=Advisory exceptions expiring::Reviewed advisory exceptions expire on $exception_expires ($days_left days). Reassess the affected operations and dependencies."
fi

audit_arguments=()
for exception_id in "${exception_ids[@]}"; do
  audit_arguments+=(--ignore "$exception_id")
done
echo "five scoped advisory exceptions valid through $exception_expires"
exec cargo audit "${audit_arguments[@]}" "$@"
