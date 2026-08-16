#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "$0")/.." && pwd)
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/declawd-sbom-checkouts.XXXXXX")
revision=$(git -C "$repository_root" rev-parse HEAD)
epoch=$(git -C "$repository_root" show -s --format=%ct HEAD)

cleanup() {
  find "$temporary_directory" -type f -delete
  find "$temporary_directory" -depth -type d -empty -delete
}
trap cleanup EXIT

for checkout in first second; do
  mkdir "$temporary_directory/$checkout"
  git -C "$repository_root" archive HEAD | tar -x -C "$temporary_directory/$checkout"
  (
    cd "$temporary_directory/$checkout"
    python3 scripts/generate-sbom.py \
      --source-revision "$revision" \
      --source-date-epoch "$epoch" \
      --output "$temporary_directory/$checkout-rust.cdx.json"
    python3 scripts/generate-python-sbom.py \
      --source-revision "$revision" \
      --source-date-epoch "$epoch" \
      --output "$temporary_directory/$checkout-python.cdx.json"
  )
done

cmp "$temporary_directory/first-rust.cdx.json" "$temporary_directory/second-rust.cdx.json"
cmp "$temporary_directory/first-python.cdx.json" "$temporary_directory/second-python.cdx.json"

echo "verified Rust and Python SBOMs across separate clean source checkouts"
