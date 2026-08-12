#!/usr/bin/env bash
set -euo pipefail

# c2pa 0.90.12's rust-native backend selects rsa 0.9.10. RUSTSEC-2023-0071
# has no patched release. The CLI neither loads private keys nor performs RSA
# private-key operations, so this exception is narrow and expires quickly.
exception_id=RUSTSEC-2023-0071
exception_expires=2026-09-12
audit_date=${DECLAWD_AUDIT_DATE:-$(date -u +%F)}

if [[ ! "$audit_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "invalid audit date: $audit_date" >&2
  exit 1
fi
if [[ "$audit_date" > "$exception_expires" ]]; then
  echo "$exception_id exception expired on $exception_expires; reassess c2pa and rsa" >&2
  exit 1
fi

echo "$exception_id exception valid through $exception_expires"
exec cargo audit --ignore "$exception_id" "$@"
