from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess
from PIL import Image
from experiment import HERE, ROOT, registration, sha


def check_state(state, expected):
    path = HERE / state["path"]
    if sha(path) != state["sha256"] or path.stat().st_size != state["bytes"]:
        raise ValueError("Retained file differs: " + str(path))
    image = Image.open(path)
    rgb = image.convert("RGB")
    if list(image.size) != state["size"] or ("A" in image.getbands()) != state["alpha"] or hashlib.sha256(rgb.tobytes()).hexdigest() != state["rgb_sha256"]:
        raise ValueError("Retained decoded pixels differ")
    python_exact = state["python"]["detected"] and state["python"]["schema"] == 2 and state["python"]["payload"] == expected
    rust_exact = state["rust"]["returncode"] == 0 and state["rust"]["stdout"].strip() == "Found watermark: " + expected
    if python_exact != state["python"]["exact"] or rust_exact != state["rust"]["exact"]:
        raise ValueError("Exact-payload classification differs")
    return rgb


def verify():
    registration()
    first_manifest = json.loads((HERE / "first-run-manifest.json").read_text())
    for name, digest in first_manifest["files"].items():
        if sha(HERE / name) != digest:
            raise ValueError("First-run file changed: " + name)
    first = json.loads((HERE / "run/results.json").read_text())
    continuation = json.loads((HERE / "png-removal/results.json").read_text())
    if len(first["controls"]) != 12 or len(first["trials"]) != 24 or first["errors"] or len(continuation["cases"]) != 18 or continuation["errors"]:
        raise ValueError("Incomplete run")
    if continuation["registration_sha256"] != sha(HERE / "png-registration.json"):
        raise ValueError("Continuation registration differs")
    png_receipt = json.loads((HERE / "png-registration.json").read_text())
    subprocess.run(["git", "merge-base", "--is-ancestor", png_receipt["input_commit"], "HEAD"], cwd=ROOT, check=True)
    for name, digest in png_receipt["files"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Continuation input changed")
        original = subprocess.check_output(["git", "show", png_receipt["input_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(original).hexdigest() != digest:
            raise ValueError("Continuation input commit differs")
    cases = {item["id"]: item for item in json.loads((HERE / "cases.json").read_text())}
    control_positives = {"python": 0, "rust": 0}
    for control in first["controls"]:
        for state in control["states"].values():
            check_state(state, cases[control["id"]]["payload"])
        source = control["states"]["source"]
        control_positives["python"] += bool(source["python"]["detected"])
        control_positives["rust"] += source["rust"]["stdout"].startswith("Found watermark:")
    for trial in first["trials"]:
        for state in trial["states"].values():
            check_state(state, trial["expected_payload"])
        signed = trial["states"]["signed"]
        raw = json.loads(signed["oracle"]["stdout"])
        successes = {x["code"] for x in raw["validation_results"]["activeManifest"]["success"]}
        if not {"claimSignature.validated", "assertion.dataHash.match"} <= successes:
            raise ValueError("Signed oracle control differs")
        if trial["states"]["cleaned"]["oracle"]["returncode"] == 0:
            raise ValueError("Cleaned oracle should find no claim")
        if signed["rgb_sha256"] != trial["states"]["marked"]["rgb_sha256"] or trial["states"]["cleaned"]["rgb_sha256"] != trial["states"]["marked"]["rgb_sha256"]:
            raise ValueError("Metadata operation changed decoded pixels")
    for row in continuation["cases"]:
        if row["errors"]:
            raise ValueError("Continuation error")
        state = {"path": row["output"], "sha256": row["output_sha256"], "bytes": row["bytes"], "rgb_sha256": row["rgb_sha256"], "size": row["size"], "alpha": row["alpha"], "python": row["python"], "rust": row["rust"]}
        rgb = check_state(state, row["expected_payload"])
        source = Image.open(ROOT / row["path"]).convert("RGB")
        mse = math.fsum((a - b) ** 2 for a, b in zip(rgb.tobytes(), source.tobytes())) / len(rgb.tobytes())
        if not math.isclose(mse, row["mse"], rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Continuation quality measurement differs")
    rows = []
    png = {(row["id"], row["encoder"]): row for row in continuation["cases"]}
    for encoder in ["python", "rust"]:
        trials = [trial for trial in first["trials"] if trial["encoder"] == encoder]
        for decoder in ["python", "rust"]:
            removed = [png[(trial["id"], encoder)][decoder]["exact"] if trial["id"].endswith("-png") else trial["states"]["removed"][decoder]["exact"] for trial in trials]
            rows.append({"encoder": encoder, "decoder": decoder, "trials": len(trials), "marked_exact": sum(t["states"]["marked"][decoder]["exact"] for t in trials), "signed_exact": sum(t["states"]["signed"][decoder]["exact"] for t in trials), "cleaned_exact": sum(t["states"]["cleaned"][decoder]["exact"] for t in trials), "pixel_removed_exact": sum(removed)})
    byte_matches = sum((HERE / trial["states"]["cleaned"]["path"]).read_bytes() == (HERE / trial["states"]["marked"]["path"]).read_bytes() for trial in first["trials"])
    psnr = [row["psnr"] for row in continuation["cases"] if row["encoder"] != "source"] + [trial["states"]["removed"]["psnr_from_reference"] for trial in first["trials"] if trial["id"].endswith("-jpg")]
    return {"schema": "declawd.trustmark-rust-summary/v1", "reviewed_on": "2026-11-13", "original_registration_sha256": sha(HERE / "registration.json"), "png_registration_sha256": sha(HERE / "png-registration.json"), "controls": 12, "encoder_trials": 24, "first_run_png_control_errors": sum(bool(x["errors"]) for x in first["controls"]), "first_run_png_trial_errors": sum(bool(x["errors"]) for x in first["trials"]), "png_continuation_inputs": 18, "png_continuation_errors": 0, "source_control_positive_flags": control_positives, "cleaned_byte_matches": byte_matches, "metadata_pixel_preservation_trials": 24, "recovery": rows, "removed_psnr_db_range": [min(x for x in psnr if x is not None), max(x for x in psnr if x is not None)], "scope": "Generated owned images, matching Q decoders and pinned runtimes. Exact-payload outcomes do not establish absence of arbitrary watermarks or a population false-positive rate."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args()
    result = verify()
    path = HERE / "summary.json"
    if args.write_summary:
        path.write_text(json.dumps(result, indent=2) + "\n")
    elif json.loads(path.read_text()) != result:
        raise ValueError("Summary differs from complete retained outcomes")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
