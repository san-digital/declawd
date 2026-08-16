#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "$0")/.." && pwd)
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/declawd-synthid-bundle.XXXXXX")

cleanup() {
  find "$temporary_directory" -type f -delete
  find "$temporary_directory" -depth -type d -empty -delete
}
trap cleanup EXIT

first="$temporary_directory/first.tar.gz"
second="$temporary_directory/second.tar.gz"
python3 "$repository_root/scripts/generate-synthid-bundle.py" --output "$first"
python3 "$repository_root/scripts/generate-synthid-bundle.py" --output "$second"
cmp "$first" "$second"

tar -tzf "$first" > "$temporary_directory/files.txt"
test "$(grep -c '^fixtures/synthid/sampling-table-v1.bin$' "$temporary_directory/files.txt")" -eq 1
test "$(grep -c '^evidence/synthid/dathathri-2024-synthid-text.pdf$' "$temporary_directory/files.txt")" -eq 1
test "$(grep -c '^fixtures/synthid/registered-edits-v1.json$' "$temporary_directory/files.txt")" -eq 1
test "$(grep -c '^reference/synthid-runner-lock-v1.json$' "$temporary_directory/files.txt")" -eq 1

echo "verified reproducible SynthID teaching bundle"
