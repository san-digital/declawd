#!/usr/bin/env python3
"""Generate a deterministic dependency notice from cargo-about and Cargo.lock."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "THIRD_PARTY_LICENSES.txt"


def cargo_about() -> dict:
    result = subprocess.run(
        ["cargo", "about", "generate", "--format", "json", "--locked", "--fail"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return json.loads(result.stdout)


def render(document: dict) -> str:
    lines = [
        "Third-party software notices",
        "============================",
        "",
        "Generated from Cargo.lock with cargo-about. Do not edit by hand.",
        "",
        "Package inventory",
        "-----------------",
        "",
    ]
    packages = []
    for entry in document["crates"]:
        package = entry["package"]
        if package["name"] == "declawd":
            continue
        link = package.get("repository") or f"https://crates.io/crates/{package['name']}"
        packages.append((package["name"], package["version"], entry["license"], link))
    for name, version, licence, link in sorted(packages, key=lambda row: (row[0], row[1])):
        lines.append(f"- {name} {version} | {licence} | {link}")

    lines.extend(["", "Licence texts", "-------------", ""])
    unique = {}
    for licence in document["licenses"]:
        text = licence["text"].replace("\r\n", "\n").replace("\r", "\n").strip()
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        unique.setdefault((licence["id"], digest), (licence["name"], text))
    for (spdx, digest), (name, text) in sorted(unique.items()):
        lines.extend([
            "=" * 79,
            f"{name} ({spdx}; text SHA-256 {digest})",
            "=" * 79,
            "",
            text,
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render(cargo_about())
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print(
                "THIRD_PARTY_LICENSES.txt is stale; run "
                "scripts/generate-third-party-licences.py",
                file=sys.stderr,
            )
            return 1
        print("third-party licence notice verified")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
