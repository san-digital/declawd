#!/usr/bin/env python3
"""Create the deterministic public SynthID teaching bundle."""
from __future__ import annotations

import argparse
import gzip
import io
from pathlib import Path
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "LICENSE",
    "NOTICE",
    "SYNTHID_THIRD_PARTY_NOTICES.md",
    "evidence/synthid/CC-BY-4.0.txt",
    "evidence/synthid/README.md",
    "evidence/synthid/dathathri-2024-synthid-text.pdf",
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
    "reference/generate_synthid_table.py",
    "reference/python-audit-tool-requirements.txt",
    "reference/synthid-runner-linux-cpu.lock",
    "reference/synthid-runner-lock-v1.json",
    "reference/synthid-runner-requirements.txt",
    "reference/synthid-runner-install-requirements.txt",
    "reference/synthid_model_runner.py",
    "reference/synthid_reference.py",
    "reference/verify_synthid_upstream.py",
    "spec/synthid-distribution-v1.schema.json",
    "spec/synthid-profile-v1.schema.json",
    "spec/synthid-score-v1.schema.json",
    "spec/synthid-trace-v1.schema.json",
    "spec/synthid-v1.md",
)


def git_epoch() -> int:
    return int(subprocess.check_output(
        ["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT, text=True
    ).strip())


def generate(destination: Path, epoch: int) -> None:
    if destination.exists():
        raise ValueError(f"refusing to overwrite {destination}")
    if not destination.parent.is_dir():
        raise ValueError(f"output directory does not exist: {destination.parent}")
    with destination.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for name in FILES:
                    data = (ROOT / name).read_bytes()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mtime = epoch
                    info.mode = 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    archive.addfile(info, io.BytesIO(data))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-date-epoch", type=int)
    args = parser.parse_args()
    destination = args.output if args.output.is_absolute() else ROOT / args.output
    epoch = args.source_date_epoch if args.source_date_epoch is not None else git_epoch()
    if epoch < 0:
        raise ValueError("source date epoch must be non-negative")
    generate(destination, epoch)
    print(f"wrote deterministic SynthID teaching bundle {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
