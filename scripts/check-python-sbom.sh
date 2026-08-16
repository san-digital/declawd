#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "$0")/.." && pwd)
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/declawd-python-sbom.XXXXXX")

cleanup() {
  find "$temporary_directory" -type f -delete
  find "$temporary_directory" -depth -type d -empty -delete
}
trap cleanup EXIT

first="$temporary_directory/first.cdx.json"
second="$temporary_directory/second.cdx.json"
python3 "$repository_root/scripts/generate-python-sbom.py" --output "$first"
python3 "$repository_root/scripts/generate-python-sbom.py" --validate "$first"
python3 "$repository_root/scripts/generate-python-sbom.py" --output "$second"
cmp "$first" "$second"

echo "verified reproducible Python CycloneDX 1.5 SBOM"
