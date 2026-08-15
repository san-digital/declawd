#!/usr/bin/env python3
"""Generate the source-contract digest manifest used for release pinning."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release-manifest-v1.json"
FILES = (
    "SYNTHID_THIRD_PARTY_NOTICES.md",
    "evidence/synthid/CC-BY-4.0.txt",
    "evidence/synthid/README.md",
    "evidence/synthid/dathathri-2024-synthid-text.pdf",
    "fixtures/c2pa/signed-fixture-manifest.json",
    "fixtures/c2pa/signed.jpg",
    "fixtures/c2pa/signed.png",
    "fixtures/c2pa/source.jpg",
    "fixtures/c2pa/source.png",
    "fixtures/profile-v1.json",
    "fixtures/synthid/distribution-v1.json",
    "fixtures/synthid/environment-v1.json",
    "fixtures/synthid/gemma-2b-it-input-v1.json",
    "fixtures/synthid/gpt2-input-v1.json",
    "fixtures/synthid/gpt2-trace-v1.json",
    "fixtures/synthid/profile-v1.json",
    "fixtures/synthid/registered-edits-v1.json",
    "fixtures/synthid/sampling-table-v1.bin",
    "fixtures/synthid/trace-eos-v1.json",
    "fixtures/synthid/trace-prepared-v1.json",
    "fixtures/synthid/trace-repeated-v1.json",
    "fixtures/synthid/trace-short-v1.json",
    "reports/calibration-report-v1.json",
    "reports/evaluation-report-v1.json",
    "reference/generate_synthid_table.py",
    "reference/python-audit-tool-requirements.txt",
    "reference/synthid-runner-linux-cpu.lock",
    "reference/synthid-runner-lock-v1.json",
    "reference/synthid-runner-install-requirements.txt",
    "reference/synthid-runner-requirements.txt",
    "reference/synthid_model_runner.py",
    "reference/synthid_reference.py",
    "reference/verify_synthid_upstream.py",
    "spec/report-v1.schema.json",
    "spec/synthid-distribution-v1.schema.json",
    "spec/synthid-profile-v1.schema.json",
    "spec/synthid-score-v1.schema.json",
    "spec/synthid-trace-v1.schema.json",
    "spec/synthid-v1.md",
    "spec/unicode-registry-v1.json",
    "vectors/controlled-removal-v1.json",
    "vectors/report-v1.json",
    "vectors/scoring-v1.json",
    "vectors/unicode-v1.json",
)


def render(release: str, source_revision: str | None) -> str:
    files = []
    for name in FILES:
        data = (ROOT / name).read_bytes()
        files.append({
            "path": name,
            "byte_length": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    document = {
        "schema": "declawd.release-manifest/v1",
        "release": release,
        "source_revision": source_revision,
        "files": files,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="v0.2.0-source-contract")
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    destination = args.output if args.output.is_absolute() else ROOT / args.output
    destination.write_text(
        render(args.release, args.source_revision), encoding="utf-8"
    )
    try:
        label = destination.relative_to(ROOT)
    except ValueError:
        label = destination
    print(f"wrote {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
