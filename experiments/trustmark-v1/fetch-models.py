#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    models = json.loads((Path(__file__).parent / "models.json").read_text())
    directory = args.source / "python/trustmark/models"
    directory.mkdir(parents=True, exist_ok=True)
    for model in models:
        path = directory / model["file"]
        if path.exists():
            data = path.read_bytes()
        else:
            with urlopen(model["url"], timeout=120) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != model["sha256"] or hashlib.md5(data).hexdigest() != model["upstream_md5"]:
            raise ValueError(f"model checksum mismatch: {model['file']}")
        path.write_bytes(data)
        print(f"verified {model['file']}")


if __name__ == "__main__":
    main()
