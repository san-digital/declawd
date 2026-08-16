#!/usr/bin/env python3
"""Generate and validate the deterministic Python runner CycloneDX SBOM."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "reference/synthid-runner-lock-v1.json"
REQUIREMENTS_PATH = ROOT / "reference/synthid-runner-linux-cpu.lock"
TOOL_VERSION = "7.3.1"
LIBRARY_VERSION = "11.12.0"
SPEC_VERSION = "1.5"
SYNTHID_COMMIT = "8f2e2316904ea7291ac96e30eb394c453dcc577b"
EXPECTED_DIRECT = {
    "immutabledict": "4.2.0",
    "jax": "0.11.0",
    "jaxlib": "0.11.0",
    "safetensors": "0.8.0",
    "torch": "2.13.0+cpu",
    "transformers": "5.15.0",
}


def package_version() -> str:
    match = re.search(
        r'^version = "([^"]+)"$',
        (ROOT / "Cargo.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError("Cargo.toml package version is missing")
    return match.group(1)


def git_value(format_string: str) -> str:
    return subprocess.check_output(
        ["git", "show", "-s", f"--format={format_string}", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def timestamp(epoch: int) -> str:
    value = datetime.fromtimestamp(epoch, timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


def purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name}@{quote(version, safe='.')}"


def load_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("schema") != "declawd.python-runtime-lock/v1":
        raise ValueError("Python runtime lock schema is wrong")
    if lock.get("environment") != {
        "implementation": "CPython",
        "python": "3.12",
        "platform": "manylinux x86_64",
        "device": "cpu",
    }:
        raise ValueError("Python runtime lock environment is wrong")
    if lock.get("indexes") != [
        "https://download.pytorch.org/whl/cpu",
        "https://pypi.org/simple",
    ]:
        raise ValueError("Python runtime lock indexes are wrong")
    packages = lock.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("Python runtime lock has no packages")
    names = [package.get("name") for package in packages]
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError("Python runtime lock package names must be sorted and unique")
    by_name = {package["name"]: package for package in packages}
    if lock.get("direct") != sorted(EXPECTED_DIRECT):
        raise ValueError("Python runtime lock direct dependency set is wrong")
    for name, version in EXPECTED_DIRECT.items():
        if by_name.get(name, {}).get("version") != version:
            raise ValueError(f"Python runtime lock does not pin {name} {version}")
    for package in packages:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", package["name"]):
            raise ValueError("Python runtime lock contains a non-canonical name")
        if not re.fullmatch(r"[0-9a-f]{64}", package.get("sha256", "")):
            raise ValueError(f"Python runtime lock does not hash {package['name']}")
        if not isinstance(package.get("licence"), str) or not package["licence"]:
            raise ValueError(f"Python runtime lock does not license {package['name']}")
        if not package.get("url", "").startswith((
            "https://files.pythonhosted.org/",
            "https://download-r2.pytorch.org/whl/cpu/",
        )):
            raise ValueError(f"Python runtime lock uses an unapproved host for {package['name']}")
        if package.get("dependencies") != sorted(set(package.get("dependencies", []))):
            raise ValueError(f"Python runtime lock dependencies are not canonical for {package['name']}")
        if set(package["dependencies"]) - set(by_name):
            raise ValueError(f"Python runtime lock has an unresolved edge for {package['name']}")
    source = lock.get("source_references")
    if source != [{
        "name": "google-deepmind/synthid-text",
        "version": "0.2.1",
        "commit": SYNTHID_COMMIT,
        "role": "frozen compatibility oracle and table provenance; not installed",
    }]:
        raise ValueError("Python runtime lock has the wrong upstream source reference")
    expected_requirements = [
        "# Generated from reference/synthid-runner-lock-v1.json for CPython 3.12 Linux x86_64 CPU.",
        "--index-url https://download.pytorch.org/whl/cpu",
        "--extra-index-url https://pypi.org/simple",
        "--only-binary :all:",
        "--require-hashes",
        "",
    ]
    expected_requirements.extend(
        f"{package['name']}=={package['version']} --hash=sha256:{package['sha256']}"
        for package in packages
    )
    if REQUIREMENTS_PATH.read_text(encoding="utf-8") != "\n".join(expected_requirements) + "\n":
        raise ValueError("hashed Python requirements do not match the runtime lock")
    return lock


def normalise(document: dict, lock: dict, version: str, revision: str, epoch: int) -> None:
    packages = lock["packages"]
    components = []
    dependencies = []
    by_name = {package["name"]: package for package in packages}
    for package in packages:
        reference = purl(package["name"], package["version"])
        components.append({
            "type": "library",
            "bom-ref": reference,
            "name": package["name"],
            "version": package["version"],
            "purl": reference,
            "hashes": [{"alg": "SHA-256", "content": package["sha256"]}],
            "licenses": [{"expression": package["licence"]}],
            "externalReferences": [{"type": "distribution", "url": package["url"]}],
        })
        dependencies.append({
            "ref": reference,
            "dependsOn": [
                purl(dependency, by_name[dependency]["version"])
                for dependency in package["dependencies"]
            ],
        })

    source_ref = "pkg:github/google-deepmind/synthid-text@0.2.1"
    components.append({
        "type": "library",
        "scope": "excluded",
        "bom-ref": source_ref,
        "name": "synthid-text",
        "version": "0.2.1",
        "purl": source_ref,
        "externalReferences": [{
            "type": "vcs",
            "url": f"https://github.com/google-deepmind/synthid-text/tree/{SYNTHID_COMMIT}",
        }],
        "properties": [
            {"name": "declawd:source_commit", "value": SYNTHID_COMMIT},
            {
                "name": "declawd:scope",
                "value": "frozen compatibility oracle and table provenance; not installed",
            },
        ],
        "licenses": [{"expression": "Apache-2.0"}],
    })
    dependencies.append({
        "ref": source_ref,
        "dependsOn": [
            purl("immutabledict", by_name["immutabledict"]["version"]),
            purl("jax", by_name["jax"]["version"]),
            purl("torch", by_name["torch"]["version"]),
            purl("transformers", by_name["transformers"]["version"]),
        ],
    })

    root_ref = f"pkg:generic/declawd-synthid-reference@{version}"
    dependencies.append({
        "ref": root_ref,
        "dependsOn": [
            *[purl(name, by_name[name]["version"]) for name in lock["direct"]],
            source_ref,
        ],
    })
    document["components"] = components
    document["dependencies"] = dependencies
    metadata = document["metadata"]
    metadata["timestamp"] = timestamp(epoch)
    metadata["component"] = {
        "type": "application",
        "name": "declawd-synthid-reference",
        "version": version,
        "bom-ref": root_ref,
        "purl": root_ref,
    }
    metadata["properties"] = [{
        "name": "declawd:source_revision",
        "value": revision,
    }]
    document.pop("serialNumber", None)
    document["version"] = 1


def validate(document: dict, lock: dict, version: str, revision: str, epoch: int) -> None:
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != SPEC_VERSION:
        raise ValueError(f"Python SBOM must be CycloneDX {SPEC_VERSION}")
    if document.get("version") != 1 or "serialNumber" in document:
        raise ValueError("Python SBOM must have version 1 and no serial number")
    metadata = document.get("metadata", {})
    if metadata.get("timestamp") != timestamp(epoch):
        raise ValueError("Python SBOM timestamp does not match SOURCE_DATE_EPOCH")
    tools = metadata.get("tools", {}).get("components", [])
    versions = {tool.get("name"): tool.get("version") for tool in tools}
    if versions.get("cyclonedx-py") != TOOL_VERSION:
        raise ValueError("unexpected cyclonedx-py version")
    if versions.get("cyclonedx-python-lib") != LIBRARY_VERSION:
        raise ValueError("unexpected cyclonedx-python-lib version")
    root_ref = f"pkg:generic/declawd-synthid-reference@{version}"
    root = metadata.get("component", {})
    if root.get("bom-ref") != root_ref or root.get("version") != version:
        raise ValueError("Python SBOM root component is wrong")
    properties = {item.get("name"): item.get("value") for item in metadata.get("properties", [])}
    if properties.get("declawd:source_revision") != revision:
        raise ValueError("Python SBOM source revision is wrong")

    packages = {package["name"]: package for package in lock["packages"]}
    component_list = document.get("components", [])
    if len(component_list) != len(packages) + 1:
        raise ValueError("Python SBOM has duplicate or missing components")
    if len({component.get("name") for component in component_list}) != len(component_list):
        raise ValueError("Python SBOM component names are not unique")
    if len({component.get("bom-ref") for component in component_list}) != len(component_list):
        raise ValueError("Python SBOM component references are not unique")
    components = {component["name"]: component for component in component_list}
    if set(components) != set(packages) | {"synthid-text"}:
        raise ValueError("Python SBOM component set differs from the resolved lock")
    for name, package in packages.items():
        component = components[name]
        expected_purl = purl(name, package["version"])
        if component.get("version") != package["version"]:
            raise ValueError(f"Python SBOM does not pin {name} {package['version']}")
        if component.get("purl") != expected_purl or component.get("bom-ref") != expected_purl:
            raise ValueError(f"Python SBOM relabels the locked {name} component")
        if component.get("externalReferences") != [{
            "type": "distribution", "url": package["url"]
        }]:
            raise ValueError(f"Python SBOM changes the locked {name} distribution")
        if component.get("hashes") != [{"alg": "SHA-256", "content": package["sha256"]}]:
            raise ValueError(f"Python SBOM does not bind the reviewed {name} archive")
        if component.get("licenses") != [{"expression": package["licence"]}]:
            raise ValueError(f"Python SBOM does not preserve the reviewed {name} licence")
    source_ref = "pkg:github/google-deepmind/synthid-text@0.2.1"
    source_component = components["synthid-text"]
    if (
        source_component.get("scope") != "excluded"
        or source_component.get("purl") != source_ref
        or source_component.get("bom-ref") != source_ref
        or source_component.get("version") != "0.2.1"
        or source_component.get("licenses") != [{"expression": "Apache-2.0"}]
        or source_component.get("externalReferences") != [{
            "type": "vcs",
            "url": f"https://github.com/google-deepmind/synthid-text/tree/{SYNTHID_COMMIT}",
        }]
        or source_component.get("properties") != [
            {"name": "declawd:source_commit", "value": SYNTHID_COMMIT},
            {
                "name": "declawd:scope",
                "value": "frozen compatibility oracle and table provenance; not installed",
            },
        ]
    ):
        raise ValueError("Python SBOM does not pin the upstream source commit")

    expected_graph = {
        purl(name, package["version"]): [
            purl(dependency, packages[dependency]["version"])
            for dependency in package["dependencies"]
        ]
        for name, package in packages.items()
    }
    expected_graph[source_ref] = [
        purl("immutabledict", packages["immutabledict"]["version"]),
        purl("jax", packages["jax"]["version"]),
        purl("torch", packages["torch"]["version"]),
        purl("transformers", packages["transformers"]["version"]),
    ]
    expected_graph[root_ref] = [
        *[purl(name, packages[name]["version"]) for name in lock["direct"]],
        source_ref,
    ]
    dependency_list = document.get("dependencies", [])
    if len(dependency_list) != len(packages) + 2:
        raise ValueError("Python SBOM has duplicate or missing dependency nodes")
    actual_graph = {
        dependency.get("ref"): dependency.get("dependsOn", [])
        for dependency in dependency_list
    }
    if len(actual_graph) != len(dependency_list):
        raise ValueError("Python SBOM dependency references are not unique")
    if actual_graph != expected_graph:
        raise ValueError("Python SBOM dependency graph differs from the resolved lock")
    try:
        from cyclonedx.schema import OutputFormat, SchemaVersion
        from cyclonedx.validation import make_schemabased_validator
    except ImportError as error:
        raise ValueError(
            "cyclonedx-python-lib 11.12.0 is required for official schema validation"
        ) from error
    validator = make_schemabased_validator(OutputFormat.JSON, SchemaVersion.V1_5)
    validation_error = validator.validate_str(
        json.dumps(document, ensure_ascii=False), all_errors=True
    )
    if validation_error is not None:
        raise ValueError(
            f"Python SBOM fails the official CycloneDX 1.5 schema: {validation_error}"
        )


def generate(destination: Path, revision: str, epoch: int) -> None:
    tool = shutil.which("cyclonedx-py")
    if not tool:
        raise ValueError(f"cyclonedx-bom {TOOL_VERSION} is required")
    if subprocess.check_output([tool, "--version"], text=True).strip() != TOOL_VERSION:
        raise ValueError(f"cyclonedx-py must be version {TOOL_VERSION}")
    if destination.exists():
        raise ValueError(f"refusing to overwrite existing SBOM: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(f"SBOM output directory does not exist: {destination.parent}")
    lock = load_lock()
    with tempfile.TemporaryDirectory(prefix="declawd-python-sbom-") as temporary:
        generated = Path(temporary) / "generated.cdx.json"
        subprocess.run(
            [
                tool,
                "requirements",
                str(REQUIREMENTS_PATH),
                "--spec-version",
                SPEC_VERSION,
                "--output-reproducible",
                "--output-format",
                "JSON",
                "--output-file",
                str(generated),
            ],
            cwd=ROOT,
            check=True,
        )
        document = json.loads(generated.read_text(encoding="utf-8"))
    version = package_version()
    normalise(document, lock, version, revision, epoch)
    validate(document, lock, version, revision, epoch)
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--source-date-epoch", type=int)
    args = parser.parse_args()
    if (args.output is None) == (args.validate is None):
        parser.error("choose exactly one of --output or --validate")
    revision = args.source_revision or git_value("%H")
    epoch = args.source_date_epoch if args.source_date_epoch is not None else int(git_value("%ct"))
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or epoch < 0:
        raise ValueError("source revision or epoch is invalid")
    version = package_version()
    lock = load_lock()
    if args.validate:
        validate(json.loads(args.validate.read_text(encoding="utf-8")), lock, version, revision, epoch)
        print(f"verified deterministic Python CycloneDX {SPEC_VERSION} SBOM")
    else:
        destination = args.output if args.output.is_absolute() else ROOT / args.output
        generate(destination, revision, epoch)
        print(f"wrote deterministic Python CycloneDX {SPEC_VERSION} SBOM {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
