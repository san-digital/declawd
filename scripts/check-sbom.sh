#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "$0")/.." && pwd)
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/declawd-sbom-check.XXXXXX")

cleanup() {
  find "$temporary_directory" -type f -delete
  find "$temporary_directory" -depth -type d -empty -delete
}
trap cleanup EXIT

first="$temporary_directory/declawd-first.cdx.json"
second="$temporary_directory/declawd-second.cdx.json"

python3 "$repository_root/scripts/generate-sbom.py" --output "$first"
python3 "$repository_root/scripts/generate-sbom.py" --validate "$first"
python3 "$repository_root/scripts/generate-sbom.py" --output "$second"
cmp "$first" "$second"

echo "verified reproducible CycloneDX 1.5 SBOM"
