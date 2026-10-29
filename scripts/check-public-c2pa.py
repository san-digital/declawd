#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(arguments):
    return subprocess.run(arguments, capture_output=True, text=True, timeout=60, cwd=ROOT)


def no_claim(path):
    result = run(["c2patool", str(path)])
    if result.returncode == 0 or "No claim found" not in result.stderr:
        raise ValueError(f"{path}: oracle did not report an absent claim")


def main():
    manifest = json.loads((ROOT / "fixtures/c2pa/public-fixture-manifest.json").read_text())
    if manifest["schema"] != "declawd.c2pa-public-fixtures/v1":
        raise ValueError("unexpected public fixture schema")
    version = run(["c2patool", "--version"])
    if version.returncode or version.stdout.strip() != f"c2patool {manifest['oracle']['version']}":
        raise ValueError("unexpected c2patool version")
    licence = ROOT / manifest["licence"]["path"]
    if hashlib.sha256(licence.read_bytes()).hexdigest() != manifest["licence"]["sha256"]:
        raise ValueError("fixture licence hash mismatch")
    declawd = str(Path(sys.argv[1]).resolve())
    for case in manifest["cases"]:
        path = ROOT / case["path"]
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != case["sha256"]:
            raise ValueError(f"{path}: fixture hash mismatch")
        origin = case["origin"]
        if "source_path" in origin:
            source = (ROOT / origin["source_path"]).read_bytes()
            if hashlib.sha256(source).hexdigest() != origin["source_sha256"]:
                raise ValueError(f"{path}: derivation source hash mismatch")
        expected = case["expected"]
        oracle = case["oracle"]
        if oracle and oracle["manifest"]:
            result = run(["c2patool", str(path)])
            if result.returncode:
                raise ValueError(f"{path}: oracle could not read embedded manifest: {result.stderr}")
            report = json.loads(result.stdout)
            label = report.get("active_manifest")
            if not label or label not in report.get("manifests", {}):
                raise ValueError(f"{path}: oracle found no active manifest")
            active = report.get("validation_results", {}).get("activeManifest", {})
            for category in ("success", "failure"):
                codes = {item["code"] for item in active.get(category, [])}
                if not set(oracle[category]) <= codes:
                    raise ValueError(f"{path}: missing {category} codes {set(oracle[category]) - codes}")
            successes = {item["code"] for item in active.get("success", [])}
            failures = {item["code"] for item in active.get("failure", [])}
            for good, bad in (("assertion.dataHash.match", "assertion.dataHash.mismatch"),
                              ("claimSignature.validated", "claimSignature.mismatch")):
                if good in oracle["success"] and bad in failures:
                    raise ValueError(f"{path}: contradictory oracle failure {bad}")
                if bad in oracle["failure"] and good in successes:
                    raise ValueError(f"{path}: contradictory oracle success {good}")
        elif oracle:
            no_claim(path)
        with tempfile.TemporaryDirectory(prefix="declawd-public-c2pa-") as directory:
            output = Path(directory) / path.name
            result = run([declawd, "clean", "c2pa", str(path), "--output", str(output), "--allow-empty", "--json"])
            if expected == "reject":
                if result.returncode == 0 or output.exists():
                    raise ValueError(f"{path}: malformed input was accepted or wrote output")
                continue
            if result.returncode:
                raise ValueError(f"{path}: clean failed: {result.stderr}")
            report = json.loads(result.stdout)
            if report["changed"] != (expected == "present"):
                raise ValueError(f"{path}: unexpected change report")
            for name in ("embedded_c2pa_absent", "non_c2pa_bytes_unchanged", "compressed_image_data_unchanged"):
                if report.get("verification", {}).get(name) is not True:
                    raise ValueError(f"{path}: missing preservation result {name}")
            if hashlib.sha256(output.read_bytes()).hexdigest() != case["cleaned_sha256"]:
                raise ValueError(f"{path}: retained bytes differ from the frozen expected output")
            no_claim(output)
        if path.read_bytes() != original:
            raise ValueError(f"{path}: input bytes changed")
        print(f"verified {case['id']}: {expected}")
    print(f"verified {len(manifest['cases'])} public and derived C2PA cases")


if __name__ == "__main__":
    main()
