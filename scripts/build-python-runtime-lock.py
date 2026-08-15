#!/usr/bin/env python3
"""Build the reviewed Linux CPU runtime lock from a pip installation report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


DIRECT = {
    "immutabledict": "4.2.0",
    "jax": "0.11.0",
    "jaxlib": "0.11.0",
    "safetensors": "0.8.0",
    "torch": "2.13.0+cpu",
    "transformers": "5.15.0",
}
SOURCE_COMMIT = "8f2e2316904ea7291ac96e30eb394c453dcc577b"
CLASSIFIER_LICENCES = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}
LICENCE_ALIASES = {
    "Apache 2.0 License": "Apache-2.0",
    "Apache-2.0": "Apache-2.0",
    "BSD": "BSD-3-Clause",
    "BSD-3-Clause": "BSD-3-Clause",
    "ISC License": "ISC",
    "MIT": "MIT",
    "MPL-2.0": "MPL-2.0",
    "MPL-2.0 AND MIT": "MPL-2.0 AND MIT",
}


def marker_environment() -> dict[str, str]:
    environment = default_environment()
    environment.update({
        "implementation_name": "cpython",
        "implementation_version": "3.12.0",
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Linux",
        "platform_version": "",
        "python_full_version": "3.12.0",
        "python_version": "3.12",
        "sys_platform": "linux",
        "extra": "",
    })
    return environment


def dependencies(metadata: dict, resolved: set[str]) -> list[str]:
    result = set()
    environment = marker_environment()
    for source in metadata.get("requires_dist", []):
        requirement = Requirement(source)
        if requirement.marker is not None and not requirement.marker.evaluate(environment):
            continue
        name = canonicalize_name(requirement.name)
        if name not in resolved:
            raise ValueError(f"resolved report omits dependency {name}")
        result.add(name)
    return sorted(result)


def licence(metadata: dict) -> str:
    expression = metadata.get("license_expression")
    if expression:
        return expression
    source = metadata.get("license")
    if source in LICENCE_ALIASES:
        return LICENCE_ALIASES[source]
    for classifier in metadata.get("classifier", []):
        if classifier in CLASSIFIER_LICENCES:
            return CLASSIFIER_LICENCES[classifier]
    raise ValueError(f"{metadata['name']} has no reviewed SPDX licence expression")


def build(report: dict) -> tuple[dict, str]:
    installs = report.get("install")
    if not isinstance(installs, list):
        raise ValueError("pip report has no install array")
    by_name = {
        canonicalize_name(item["metadata"]["name"]): item
        for item in installs
    }
    if len(by_name) != len(installs):
        raise ValueError("pip report repeats a package name")
    for name, version in DIRECT.items():
        if by_name.get(name, {}).get("metadata", {}).get("version") != version:
            raise ValueError(f"pip report does not pin {name} {version}")

    packages = []
    for name in sorted(by_name):
        item = by_name[name]
        download = item["download_info"]
        digest = download.get("archive_info", {}).get("hashes", {}).get("sha256")
        url = download.get("url")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"{name} has no exact SHA-256 archive binding")
        if not isinstance(url, str) or not url.startswith((
            "https://files.pythonhosted.org/",
            "https://download-r2.pytorch.org/whl/cpu/",
        )):
            raise ValueError(f"{name} uses an unapproved package host")
        packages.append({
            "name": name,
            "version": item["metadata"]["version"],
            "sha256": digest,
            "url": url,
            "licence": licence(item["metadata"]),
            "dependencies": dependencies(item["metadata"], set(by_name)),
        })

    document = {
        "schema": "declawd.python-runtime-lock/v1",
        "environment": {
            "implementation": "CPython",
            "python": "3.12",
            "platform": "manylinux x86_64",
            "device": "cpu",
        },
        "indexes": [
            "https://download.pytorch.org/whl/cpu",
            "https://pypi.org/simple",
        ],
        "direct": sorted(DIRECT),
        "source_references": [{
            "name": "google-deepmind/synthid-text",
            "version": "0.2.1",
            "commit": SOURCE_COMMIT,
            "role": "frozen compatibility oracle and table provenance; not installed",
        }],
        "packages": packages,
    }
    requirements = [
        "# Generated from reference/synthid-runner-lock-v1.json for CPython 3.12 Linux x86_64 CPU.",
        "--index-url https://download.pytorch.org/whl/cpu",
        "--extra-index-url https://pypi.org/simple",
        "--only-binary :all:",
        "--require-hashes",
        "",
    ]
    for package in packages:
        requirements.append(
            f"{package['name']}=={package['version']} --hash=sha256:{package['sha256']}"
        )
    return document, "\n".join(requirements) + "\n"


def write_new(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--requirements-output", type=Path, required=True)
    args = parser.parse_args()
    document, requirements = build(json.loads(args.report.read_text(encoding="utf-8")))
    write_new(args.json_output, json.dumps(document, indent=2) + "\n")
    write_new(args.requirements_output, requirements)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
