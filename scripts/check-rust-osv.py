#!/usr/bin/env python3
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.7.0"
RSA_IDS = {
    "RUSTSEC-2023-0071", "CVE-2023-49092",
    "GHSA-4grx-2x9w-596c", "GHSA-c38w-74pg-36hr",
}
BLOCK_BUFFER_CHECKSUM = "3078c7629b62d3f0439517fa394996acacc5cbc91c5a20d8c658e77abd503a71"


def inventory(lock):
    packages = tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
    expected = Counter()
    checksums = {}
    for package in packages:
        source = package.get("source")
        if source != "registry+https://github.com/rust-lang/crates.io-index":
            if source is not None or package["name"] != "declawd":
                raise ValueError("OSV inventory needs review for a non-crates.io dependency")
        key = ("crates.io", package["name"], package["version"])
        expected[key] += 1
        checksums[key] = package.get("checksum")
    if not expected:
        raise ValueError("Cargo.lock contains no packages")
    return expected, checksums


def review(report, lock):
    expected, checksums = inventory(lock)
    results = report.get("results")
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError("OSV must report exactly one Cargo.lock inventory")
    result = results[0]
    source = result.get("source", {})
    if source.get("type") != "lockfile" or Path(source.get("path", "")).resolve() != lock.resolve():
        raise ValueError("OSV reported an unexpected source")
    packages = result.get("packages")
    if not isinstance(packages, list):
        raise ValueError("OSV returned no package inventory")
    actual = Counter()
    findings = []
    for entry in packages:
        package = entry["package"]
        key = (package["ecosystem"], package["name"], package["version"])
        actual[key] += 1
        vulnerabilities = entry.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            raise ValueError("OSV returned an invalid vulnerability list")
        for vulnerability in vulnerabilities:
            identifier = vulnerability["id"]
            aliases = vulnerability.get("aliases", [])
            if not isinstance(identifier, str) or not isinstance(aliases, list):
                raise ValueError("OSV returned invalid advisory identifiers")
            identifiers = {identifier, *aliases}
            decision = "blocked"
            if key == ("crates.io", "rsa", "0.9.10") and identifiers <= RSA_IDS:
                decision = "reviewed_rsa_exception_until_2026-11-28"
            elif (
                key == ("crates.io", "block-buffer", "0.10.4")
                and identifier == "GHSA-qwgh-2vcv-g2f7"
                and not aliases
                and checksums.get(key) == BLOCK_BUFFER_CHECKSUM
            ):
                decision = "outside_upstream_affected_range_0.11.0_to_0.12.1"
            elif identifier == "RUSTSEC-2024-0370" and key[1] == "proc-macro-error":
                affected = vulnerability.get("affected", [])
                if affected and all(
                    item.get("database_specific", {}).get("informational") == "unmaintained"
                    for item in affected
                ):
                    decision = "informational_unmaintained"
            findings.append({
                "package": package, "id": identifier,
                "aliases": aliases, "decision": decision,
            })
    if actual != expected:
        raise ValueError(f"OSV inventory differs from Cargo.lock: missing={expected - actual}, extra={actual - expected}")
    return findings, sum(actual.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run(["bash", "scripts/check-security-advisories.sh", "--policy-only"], cwd=ROOT, check=True)
    scanner = os.environ.get("OSV_SCANNER", "osv-scanner")
    version = subprocess.check_output([scanner, "--version"], text=True)
    if version.splitlines()[0] != f"osv-scanner version: {VERSION}":
        raise ValueError(f"OSV-Scanner must be {VERSION}")
    with tempfile.TemporaryDirectory(prefix="declawd-osv-") as directory:
        config = Path(directory) / "empty.toml"
        config.write_text("", encoding="utf-8")
        result = subprocess.run([
            scanner, "scan", "source", "--lockfile=Cargo.lock",
            "--format=json", "--all-packages", "--all-vulns",
            "--no-call-analysis=all", f"--config={config}",
        ], cwd=ROOT, text=True, capture_output=True, timeout=180)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.stdout, encoding="utf-8")
    if result.returncode not in (0, 1):
        raise RuntimeError(f"OSV scan failed ({result.returncode}): {result.stderr}")
    findings, count = review(json.loads(result.stdout), ROOT / "Cargo.lock")
    summary = {
        "schema": "declawd.rust-osv-review/v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scanner_version": VERSION,
        "cargo_lock_sha256": hashlib.sha256((ROOT / "Cargo.lock").read_bytes()).hexdigest(),
        "audited_packages": count,
        "findings": findings,
    }
    args.output.with_suffix(".review.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for finding in findings:
        print(f"{finding['id']} {finding['package']['name']} {finding['package']['version']}: {finding['decision']}")
    if any(finding["decision"] == "blocked" for finding in findings):
        raise SystemExit("OSV found an advisory requiring review")
    print(f"verified OSV advisory status for all {count} Cargo.lock packages")


if __name__ == "__main__":
    main()
