#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("trustmark_experiment", HERE / "experiment.py")
EXPERIMENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPERIMENT)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_record(root, record):
    path = (root / record["path"]).resolve()
    require(path.is_relative_to(root.resolve()), "record path escapes evidence directory")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == record["sha256"], f"hash mismatch: {record['path']}")
    require(len(data) == record["bytes"], f"length mismatch: {record['path']}")
    return path


def oracle_facts(path):
    raw = json.loads(path.read_text())
    if raw["returncode"]:
        require("No claim found" in raw["stderr"], "unexpected saved oracle error")
        return {"embedded_manifest": False, "binding": "no claim", "signature": "no claim", "credential": "no claim"}, None
    report = json.loads(raw["stdout"])
    label = report.get("active_manifest")
    require(label in report.get("manifests", {}), "saved oracle has no active manifest")
    active = report.get("validation_results", {}).get("activeManifest", {})
    good = {entry["code"] for entry in active.get("success", [])}
    bad = {entry["code"] for entry in active.get("failure", [])}
    facts = {"embedded_manifest": True,
             "binding": "mismatch" if "assertion.dataHash.mismatch" in bad else "match" if "assertion.dataHash.match" in good else "unavailable",
             "signature": "mismatch" if "claimSignature.mismatch" in bad else "validated" if "claimSignature.validated" in good else "unavailable",
             "credential": "untrusted" if "signingCredential.untrusted" in bad else "trusted" if "signingCredential.trusted" in good else "unavailable"}
    return facts, report["manifests"][label]


def verify(root=HERE, pixels=False):
    registration = json.loads((root / "registration.json").read_text())
    require(registration["schema"] == "declawd.trustmark-registration/v1", "unexpected registration schema")
    for record in registration["files"] + [case["source"] for case in registration["cases"]]:
        checked_record(root, record)
    run = root / "run"
    result = json.loads((run / "results.json").read_text())
    require(result["schema"] == "declawd.trustmark-results/v1", "unexpected results schema")
    require("execution_error" not in result, "experiment execution failed")
    require(result["registration_sha256"] == hashlib.sha256((root / "registration.json").read_bytes()).hexdigest(), "registration hash mismatch")
    expected = {case["id"]: case for case in registration["cases"]}
    require(len(result["cases"]) == len(expected) == 12, "incomplete case inventory")
    require({case["id"] for case in result["cases"]} == set(expected), "case inventory mismatch")
    recorded = {record["path"] for record in result["files"]}
    actual = {str(path.relative_to(run)) for path in run.rglob("*") if path.is_file() and path.name != "results.json"}
    require(recorded == actual and len(recorded) == len(result["files"]), "run file inventory mismatch")
    for record in result["files"]:
        checked_record(run, record)
    for case in result["cases"]:
        identifier = case["id"]
        plan = expected[identifier]
        require(case["expected_payload"] == plan["payload"], f"payload registration changed: {identifier}")
        require(set(case["states"]) == set(registration["states"]), "state inventory mismatch")
        paths = {}
        for state, entry in case["states"].items():
            path = checked_record(run, entry)
            paths[state] = path
            if state == "source":
                require(path.read_bytes() == (root / plan["source"]["path"]).read_bytes(), "source bytes differ from registration")
            decoded = entry["decode"]
            exact = decoded["detected"] is True and decoded["payload"] == plan["payload"] and decoded["schema"] == 2
            require(decoded["exact_payload"] == exact, f"incorrect payload match: {identifier}/{state}")
            facts, manifest = oracle_facts(run / identifier / f"oracle-{state}.json")
            require(entry["c2pa"] == facts, f"oracle facts differ: {identifier}/{state}")
            if state == "signed":
                require(facts["embedded_manifest"] and facts["binding"] == "match" and facts["signature"] == "validated", "signed C2PA validation failed")
                assertions = [item["data"] for item in manifest["assertions"] if item["label"] == "c2pa.soft-binding"]
                require(len(assertions) == 1 and assertions[0]["alg"] == "com.adobe.trustmark.Q", "soft-binding algorithm mismatch")
                require(assertions[0]["blocks"][0]["value"] == "2*" + plan["payload"], "soft-binding payload mismatch")
            else:
                require(facts["embedded_manifest"] is False, "unexpected embedded claim")
            if pixels:
                from PIL import Image
                image = Image.open(path).convert("RGB")
                require(hashlib.sha256(image.tobytes()).hexdigest() == entry["pixel_sha256"], f"pixel hash mismatch: {identifier}/{state}")
                require(list(image.size) == plan["size"], "image dimensions changed")
        require(paths["marked"].read_bytes() == paths["cleaned"].read_bytes(), f"cleaning changed retained bytes: {identifier}")
        for state in ("signed", "cleaned"):
            require(case["states"][state]["decode"] == case["states"]["marked"]["decode"], "decoder results changed across signing or removal")
        relationships = {
            "cleaned_equals_marked": paths["marked"].read_bytes() == paths["cleaned"].read_bytes(),
            "signed_pixels_equal_marked": case["states"]["signed"]["pixel_sha256"] == case["states"]["marked"]["pixel_sha256"],
            "cleaned_pixels_equal_signed": case["states"]["cleaned"]["pixel_sha256"] == case["states"]["signed"]["pixel_sha256"],
        }
        require(case["relationships"] == relationships and all(relationships.values()), "image preservation relationship failed")
        clean = json.loads((run / identifier / "clean-report.json").read_text())
        require(clean["verification"] == case["clean_verification"], "clean verification summary changed")
        for name in ("embedded_c2pa_absent", "non_c2pa_bytes_unchanged", "compressed_image_data_unchanged"):
            require(clean["verification"][name] is True, f"missing cleaning verification: {name}")
    summary = EXPERIMENT.summary(result["cases"])
    require(result["summary"] == summary, "results summary differs from case outcomes")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pixels", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(pixels=args.pixels)))
