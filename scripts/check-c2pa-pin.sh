#!/usr/bin/env bash
set -euo pipefail

manifest_pin=$(sed -nE 's/^c2pa = \{ version = "=([^"]+)".*/\1/p' Cargo.toml)
lock_pin=$(awk '
  $0 == "name = \"c2pa\"" { in_c2pa = 1; next }
  in_c2pa && /^version = / { gsub(/^version = \"|\"$/, ""); print; exit }
' Cargo.lock)

if [[ -z "$manifest_pin" || -z "$lock_pin" ]]; then
  echo "could not resolve c2pa versions from Cargo.toml and Cargo.lock" >&2
  exit 1
fi

if [[ "$manifest_pin" != "$lock_pin" ]]; then
  echo "c2pa pin drift: Cargo.toml=$manifest_pin Cargo.lock=$lock_pin" >&2
  exit 1
fi

echo "c2pa pin verified: $manifest_pin"
