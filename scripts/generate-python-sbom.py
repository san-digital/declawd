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


ROOT = Path(__file__).resolve().parents[1]
TOOL_VERSION = "7.3.1"
LIBRARY_VERSION = "11.12.0"
SPEC_VERSION = "1.5"


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


def normalise(document: dict, version: str, revision: str, epoch: int) -> None:
    refs: dict[str, str] = {}
    for component in document["components"]:
        old = component["bom-ref"]
        if component["name"] == "synthid-text":
            component["version"] = "0.2.1"
        stable = component["purl"]
        component["bom-ref"] = stable
        refs[old] = stable
    for dependency in document["dependencies"]:
        dependency["ref"] = refs[dependency["ref"]]

    root_ref = f"pkg:generic/declawd-synthid-reference@{version}"
    document["dependencies"].append({
        "ref": root_ref,
        "dependsOn": sorted(refs.values()),
    })
    metadata = document["metadata"]
    metadata["timestamp"] = timestamp(epoch)
    metadata["component"] = {
        "type": "application",
        "name": "declawd-synthid-reference",
        "version": version,
        "bom-ref": root_ref,
        "purl": root_ref,
    }
    metadata.setdefault("properties", []).append({
        "name": "declawd:source_revision",
        "value": revision,
    })
    document.pop("serialNumber", None)
    document["version"] = 1


def validate(document: dict, version: str, revision: str, epoch: int) -> None:
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
    components = {item.get("name"): item for item in document.get("components", [])}
    expected = {
        "synthid-text": "0.2.1",
        "immutabledict": "4.2.0",
        "torch": "2.4.0",
        "transformers": "4.43.3",
    }
    for name, expected_version in expected.items():
        if components.get(name, {}).get("version") != expected_version:
            raise ValueError(f"Python SBOM does not pin {name} {expected_version}")
    refs = {item["bom-ref"] for item in document["components"]} | {root_ref}
    for dependency in document.get("dependencies", []):
        if dependency.get("ref") not in refs:
            raise ValueError("Python SBOM dependency has an unknown reference")
        if set(dependency.get("dependsOn", [])) - refs:
            raise ValueError("Python SBOM dependency points to an unknown reference")
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
    with tempfile.TemporaryDirectory(prefix="declawd-python-sbom-") as temporary:
        generated = Path(temporary) / "generated.cdx.json"
        subprocess.run(
            [
                tool,
                "requirements",
                str(ROOT / "reference/synthid-runner-requirements.txt"),
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
    normalise(document, version, revision, epoch)
    validate(document, version, revision, epoch)
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


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
    if args.validate:
        validate(json.loads(args.validate.read_text(encoding="utf-8")), version, revision, epoch)
        print(f"verified deterministic Python CycloneDX {SPEC_VERSION} SBOM")
    else:
        destination = args.output if args.output.is_absolute() else ROOT / args.output
        generate(destination, revision, epoch)
        print(f"wrote deterministic Python CycloneDX {SPEC_VERSION} SBOM {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
