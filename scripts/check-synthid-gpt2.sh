#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "$0")/.." && pwd)
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/declawd-gpt2-oracle.XXXXXX")
: "${DECLAWD_SYNTHID_UPSTREAM:?set DECLAWD_SYNTHID_UPSTREAM to the pinned upstream checkout}"

cleanup() {
  find "$temporary_directory" -type f -delete
  find "$temporary_directory" -depth -type d -empty -delete
}
trap cleanup EXIT

generated="$temporary_directory/gpt2-trace-v1.json"
python3 "$repository_root/reference/synthid_model_runner.py" \
  --model gpt2 \
  --input "$repository_root/fixtures/synthid/gpt2-input-v1.json" \
  --output "$generated" \
  --max-new-tokens 64 \
  --seed 20260815 \
  --device cpu
python3 - "$generated" "$repository_root/fixtures/synthid/gpt2-trace-v1.json" <<'PY'
import json
from pathlib import Path
import sys

generated = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
committed = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if generated != committed:
    raise SystemExit("generated GPT-2 token trace differs from the committed fixture")
PY
cmp "$generated" "$repository_root/fixtures/synthid/gpt2-trace-v1.json"
python3 "$repository_root/reference/synthid_reference.py" "$generated" > /dev/null
python3 "$repository_root/reference/verify_synthid_upstream.py" \
  --upstream "$DECLAWD_SYNTHID_UPSTREAM" \
  --trace "$repository_root/fixtures/synthid/trace-prepared-v1.json"

echo "verified pinned GPT-2 trace and DeepMind 0.2.1 oracle"
