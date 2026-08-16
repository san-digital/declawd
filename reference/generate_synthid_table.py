#!/usr/bin/env python3
"""Generate the pinned CPU SynthID sampling table.

This is a provenance tool, not a runtime dependency. Release code consumes the
committed bitset and never regenerates it.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


TABLE_SIZE = 2**16
EXPECTED_TORCH = "2.4.0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"refusing to overwrite {args.output}")
    if not args.output.parent.is_dir():
        raise ValueError(f"output directory does not exist: {args.output.parent}")

    import torch  # Imported late so --help works without the provenance stack.

    if torch.__version__.split("+", 1)[0] != EXPECTED_TORCH:
        raise ValueError(
            f"expected torch {EXPECTED_TORCH}, found {torch.__version__}"
        )
    generator = torch.Generator(device="cpu").manual_seed(0)
    bits = torch.randint(
        low=0,
        high=2,
        size=(TABLE_SIZE,),
        generator=generator,
        device="cpu",
    ).tolist()
    packed = bytearray(TABLE_SIZE // 8)
    for index, bit in enumerate(bits):
        packed[index // 8] |= int(bit) << (index % 8)
    args.output.write_bytes(packed)
    print(f"bytes={len(packed)} sha256={hashlib.sha256(packed).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
