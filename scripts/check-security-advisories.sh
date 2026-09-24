#!/usr/bin/env bash
set -euo pipefail

# RUSTSEC-2023-0071 (rsa, Marvin timing attack) has no patched release. It
# enters this crate only through c2pa: rsa 0.9.10 <- c2pa 0.90.15 <- declawd.
#
# Reassessed on 24 September 2026, after the first exception lapsed on 12
# September:
#
# - The attack recovers a private key by timing RSA private-key operations.
#   Declawd holds no keys and signs nothing.
# - Declawd calls two c2pa functions, jumbf_io::load_jumbf_from_memory and
#   jumbf_io::remove_jumbf_from_file. Both resolve to asset I/O handlers
#   (get_cailoader_handler and read_cai, get_assetio_handler and
#   remove_cai_store). The signing code in that module is test-only and is not
#   compiled into the release binary. rsa is linked into the binary, but no
#   Declawd code path calls it.
# - Upgrading does not remove it. On native targets rsa is an optional c2pa
#   dependency, turned on by the rust_native_crypto feature that Declawd
#   enables, and c2pa 0.90.22 keeps that arrangement. Its only non-optional
#   rsa entry is for wasm32, which Declawd does not build. rsa 0.9.10 and
#   0.10.0-rc.18 remain affected.
# - No other advisory is present in Cargo.lock.
#
# The exception stays short on purpose, so that each renewal is a fresh
# reassessment rather than a date moved forward. Reassess against the same four
# points before extending it.
exception_id=RUSTSEC-2023-0071
exception_expires=2026-10-24
warn_days=14
audit_date=${DECLAWD_AUDIT_DATE:-$(date -u +%F)}

if [[ ! "$audit_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "invalid audit date: $audit_date" >&2
  exit 1
fi
if [[ "$audit_date" > "$exception_expires" ]]; then
  echo "$exception_id exception expired on $exception_expires; reassess c2pa and rsa" >&2
  exit 1
fi

# The first exception lapsed with nobody noticing until every pull request
# failed at once. For its last two weeks the check still passes, but raises a
# workflow annotation that shows on each run's summary page.
# BSD date fills the time fields it is not given from the current clock, so
# both dates are pinned to midnight UTC. Otherwise two calls that straddle a
# second can make the difference one second short and drop a whole day.
midnight() {
  date -u -d "$1 00:00:00" +%s 2>/dev/null || date -u -j -f "%F %T" "$1 00:00:00" +%s
}
days_left=$(( ( $(midnight "$exception_expires") - $(midnight "$audit_date") ) / 86400 ))
if (( days_left <= warn_days )); then
  echo "::warning title=Advisory exception expiring::$exception_id exception expires on $exception_expires ($days_left days). Reassess c2pa and rsa before then."
fi

echo "$exception_id exception valid through $exception_expires"
exec cargo audit --ignore "$exception_id" "$@"
