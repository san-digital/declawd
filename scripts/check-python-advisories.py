#!/usr/bin/env python3
"""Audit every locked Python runtime component and fail on skips."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "reference/synthid-runner-lock-v1.json"
TOOL_VERSION = "2.10.1"


def main() -> int:
    version = subprocess.check_output(["pip-audit", "--version"], text=True).strip()
    if version != f"pip-audit {TOOL_VERSION}":
        raise ValueError(f"pip-audit must be {TOOL_VERSION}, found {version}")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    expected = {}
    lines = []
    canonicalised = []
    for package in lock["packages"]:
        version = package["version"]
        if package["name"] == "torch":
            if version != "2.13.0+cpu":
                raise ValueError("the only permitted audit mapping is torch 2.13.0+cpu")
            version = "2.13.0"
            canonicalised.append("torch:2.13.0+cpu->2.13.0")
        expected[package["name"]] = version
        lines.append(f"{package['name']}=={version}")
    if canonicalised != ["torch:2.13.0+cpu->2.13.0"]:
        raise ValueError("unexpected local-version audit mapping")

    with tempfile.TemporaryDirectory(prefix="declawd-python-audit-") as temporary:
        requirements = Path(temporary) / "requirements.txt"
        requirements.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run(
            [
                "pip-audit",
                "--requirement", str(requirements),
                "--vulnerability-service", "osv",
                "--format", "json",
                "--progress-spinner", "off",
                "--no-deps",
                "--disable-pip",
                "--strict",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
    if result.returncode != 0:
        raise RuntimeError(
            "Python advisory audit failed:\n"
            f"{result.stdout}{result.stderr}"
        )
    report = json.loads(result.stdout)
    dependencies = report.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("pip-audit returned no dependency inventory")
    audited = {item.get("name"): item.get("version") for item in dependencies}
    if audited != expected or len(dependencies) != len(expected):
        missing = sorted(set(expected) - set(audited))
        extra = sorted(set(audited) - set(expected))
        raise ValueError(
            f"pip-audit skipped or added components; missing={missing}, extra={extra}"
        )
    if any(item.get("vulns") for item in dependencies):
        raise RuntimeError("pip-audit returned vulnerabilities with a successful status")
    print(
        "verified OSV advisory status for all 40 locked Python packages "
        "(torch local version audited as 2.13.0)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
