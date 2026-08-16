#!/usr/bin/env python3
"""Validate the committed Python runtime closure without resolving an index."""
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "reference/synthid-runner-lock-v1.json"
REQUIREMENTS = ROOT / "reference/synthid-runner-linux-cpu.lock"
COMMIT = "8f2e2316904ea7291ac96e30eb394c453dcc577b"
DIRECT = {
    "immutabledict": "4.2.0",
    "jax": "0.11.0",
    "jaxlib": "0.11.0",
    "safetensors": "0.8.0",
    "torch": "2.13.0+cpu",
    "transformers": "5.15.0",
}
HOSTS = (
    "https://files.pythonhosted.org/",
    "https://download-r2.pytorch.org/whl/cpu/",
)


def main() -> int:
    document = json.loads(LOCK.read_text(encoding="utf-8"))
    if document.get("schema") != "declawd.python-runtime-lock/v1":
        raise ValueError("runtime lock schema is wrong")
    if document.get("environment") != {
        "implementation": "CPython",
        "python": "3.12",
        "platform": "manylinux x86_64",
        "device": "cpu",
    }:
        raise ValueError("runtime lock environment is wrong")
    if document.get("indexes") != [
        "https://download.pytorch.org/whl/cpu",
        "https://pypi.org/simple",
    ]:
        raise ValueError("runtime lock indexes are wrong")
    if document.get("direct") != sorted(DIRECT):
        raise ValueError("runtime lock direct roots are wrong")
    packages = document.get("packages")
    if not isinstance(packages, list) or len(packages) != 40:
        raise ValueError("runtime lock must contain the reviewed 40-package closure")
    names = [package.get("name") for package in packages]
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError("runtime package names must be sorted and unique")
    by_name = {package["name"]: package for package in packages}
    for name, version in DIRECT.items():
        if by_name.get(name, {}).get("version") != version:
            raise ValueError(f"runtime lock does not pin {name} {version}")
    for package in packages:
        if not package.get("url", "").startswith(HOSTS):
            raise ValueError(f"runtime lock uses an unapproved host for {package['name']}")
        if not re.fullmatch(r"[0-9a-f]{64}", package.get("sha256", "")):
            raise ValueError(f"runtime lock does not hash {package['name']}")
        if not isinstance(package.get("licence"), str) or not package["licence"]:
            raise ValueError(f"runtime lock does not license {package['name']}")
        edges = package.get("dependencies")
        if not isinstance(edges, list) or edges != sorted(set(edges)):
            raise ValueError(f"runtime lock edges are not canonical for {package['name']}")
        if set(edges) - set(by_name):
            raise ValueError(f"runtime lock has an unresolved edge for {package['name']}")
    if document.get("source_references") != [{
        "name": "google-deepmind/synthid-text",
        "version": "0.2.1",
        "commit": COMMIT,
        "role": "frozen compatibility oracle and table provenance; not installed",
    }]:
        raise ValueError("runtime lock has the wrong frozen source reference")
    expected = [
        "# Generated from reference/synthid-runner-lock-v1.json for CPython 3.12 Linux x86_64 CPU.",
        "--index-url https://download.pytorch.org/whl/cpu",
        "--extra-index-url https://pypi.org/simple",
        "--only-binary :all:",
        "--require-hashes",
        "",
    ]
    expected.extend(
        f"{package['name']}=={package['version']} --hash=sha256:{package['sha256']}"
        for package in packages
    )
    if REQUIREMENTS.read_text(encoding="utf-8") != "\n".join(expected) + "\n":
        raise ValueError("hashed requirements differ from the reviewed runtime lock")
    print("verified 40-package Python runtime closure and frozen source reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
