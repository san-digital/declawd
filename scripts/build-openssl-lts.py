#!/usr/bin/env python3
"""Build the pinned OpenSSL LTS source as static libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "aarch64-apple-darwin": "darwin64-arm64-cc",
    "x86_64-apple-darwin": "darwin64-x86_64-cc",
    "x86_64-unknown-linux-gnu": "linux-x86_64",
    "x86_64-pc-windows-msvc": "VC-WIN64A",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--github-env", action="store_true")
    args = parser.parse_args()
    host = next(line.split(": ", 1)[1] for line in subprocess.check_output(
        ["rustc", "-vV"], text=True).splitlines() if line.startswith("host: "))
    target = args.target or host
    if target not in TARGETS:
        raise ValueError(f"unsupported build target: {target}")
    prefix = args.prefix.resolve()
    if prefix.exists():
        raise ValueError(f"refusing to reuse an existing prefix: {prefix}")
    pin = json.loads((ROOT / "native/openssl-lts.json").read_text())
    with tempfile.TemporaryDirectory(prefix="declawd-openssl-") as temporary:
        work = Path(temporary)
        archive = work / "source.tar.gz"
        urllib.request.urlretrieve(pin["source_url"], archive)
        if sha256(archive) != pin["sha256"]:
            raise ValueError("OpenSSL source checksum differs from the reviewed pin")
        with tarfile.open(archive) as bundle:
            bundle.extractall(work / "source", filter="data")
        source, = (work / "source").iterdir()
        version = dict(line.split("=", 1) for line in (source / "VERSION.dat").read_text().splitlines() if "=" in line)
        actual = f'{version["MAJOR"]}.{version["MINOR"]}.{version["PATCH"]}-{version["PRE_RELEASE_TAG"]}'
        if actual != pin["version"]:
            raise ValueError(f"unexpected OpenSSL source version: {actual}")
        flags = ["no-shared", "no-module", "no-tests", "no-legacy", "--libdir=lib", f"--prefix={prefix.as_posix()}"]
        if target.endswith("windows-msvc"):
            flags.insert(0, "no-asm")
        subprocess.run([os.environ.get("PERL", "perl"), "Configure", TARGETS[target], *flags], cwd=source, check=True)
        make = ["nmake"] if target.endswith("windows-msvc") else ["make", "-j4"]
        subprocess.run([*make, "build_libs"], cwd=source, check=True)
        subprocess.run([*make, "install_dev"], cwd=source, check=True)
        libraries = ["libcrypto.lib", "libssl.lib"] if target.endswith("windows-msvc") else ["libcrypto.a", "libssl.a"]
        receipt = {**pin, "target": target, "configure": flags[:-1], "libraries": {
            name: sha256(prefix / "lib" / name) for name in libraries}}
        (prefix / "openssl-build.json").write_text(json.dumps(receipt, indent=2) + "\n")
        shutil.copy(ROOT / "native/OPENSSL-LICENSE.txt", prefix / "OPENSSL-LICENSE.txt")
    variables = {"OPENSSL_NO_VENDOR": "1", "OPENSSL_STATIC": "1"}
    if args.target is None:
        variables["OPENSSL_DIR"] = str(prefix)
    variables[f'{target.upper().replace("-", "_")}_OPENSSL_DIR'] = str(prefix)
    if args.github_env:
        with open(os.environ["GITHUB_ENV"], "a") as output:
            for key, value in variables.items():
                output.write(f"{key}={value}\n")
    print(json.dumps({"prefix": str(prefix), "environment": variables, "version": pin["version"]}))


if __name__ == "__main__":
    main()
