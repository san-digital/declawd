from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261113


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def call(arguments):
    result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True, timeout=180)
    return {"arguments": [str(x) for x in arguments], "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def require(result):
    if result["returncode"]:
        raise ValueError(result)
    return result


def registration():
    receipt = json.loads((HERE / "registration.json").read_text())
    subprocess.run(["git", "merge-base", "--is-ancestor", receipt["input_commit"], "HEAD"], cwd=ROOT, check=True)
    for name, digest in receipt["files"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Registered input differs: " + name)
        original = subprocess.check_output(["git", "show", receipt["input_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(original).hexdigest() != digest:
            raise ValueError("Input commit differs: " + name)
    committed = subprocess.check_output(["git", "show", "HEAD:experiments/trustmark-rust-v1/registration.json"], cwd=ROOT)
    if committed != (HERE / "registration.json").read_bytes():
        raise ValueError("Registration must be committed before inference")
    return receipt


def save_image(image, path):
    if path.suffix == ".png":
        image.save(path, compress_level=9)
    else:
        image.convert("RGB").save(path, quality=95, subsampling=0, optimize=False, progressive=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--rust", type=Path, required=True)
    parser.add_argument("--declawd", type=Path, required=True)
    parser.add_argument("--c2patool", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    registration()
    runtime = json.loads((HERE / "runtime.json").read_text())
    for name in ["rust", "declawd", "c2patool"]:
        if sha(getattr(args, name)) != runtime["binaries"][name]:
            raise ValueError("Binary differs: " + name)
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.source, text=True).strip() != runtime["upstream_revision"]:
        raise ValueError("Upstream revision differs")
    for name, digest in runtime["source_files"].items():
        if sha(args.source / name) != digest:
            raise ValueError("Upstream code differs: " + name)
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "python"], cwd=args.source, check=True, stdout=subprocess.DEVNULL)
    if sha(args.source / "rust/Cargo.lock") != sha(HERE / "rust-Cargo.lock"):
        raise ValueError("Experiment dependency lock differs")
    models = json.loads((HERE / "models.json").read_text())
    model_hashes = {item["name"]: item["sha256"] for item in models}
    for item in models:
        directory = args.models if item["name"].endswith(".onnx") else args.source / "python/trustmark/models"
        if sha(directory / item["name"]) != item["sha256"]:
            raise ValueError("Model differs: " + item["name"])
    for line in (HERE / "requirements-macos-arm64.lock").read_text().splitlines():
        name, rest = line.split("==", 1)
        version = rest.split()[0]
        if importlib.metadata.version(name) != version:
            raise ValueError("Python package differs: " + name)
    output = HERE / "run"
    if output.exists():
        raise ValueError("Output already exists")
    with (HERE / "attempt.json").open("x") as stream:
        json.dump({"started_at": datetime.now(timezone.utc).isoformat(), "seed": SEED, "registration_sha256": sha(HERE / "registration.json")}, stream, indent=2)
    output.mkdir()
    result = {"schema": "declawd.trustmark-rust-result/v1", "registration_sha256": sha(HERE / "registration.json"), "platform": {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine()}, "controls": [], "trials": [], "errors": []}
    try:
        os.environ["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
        sys.path.insert(0, str(args.source / "python"))
        import torch
        from PIL import Image
        from trustmark import TrustMark
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.manual_seed(SEED)
        torch.use_deterministic_algorithms(True)

        def local_only(self, filename):
            if sha(Path(filename)) != model_hashes[Path(filename).name]:
                raise ValueError("Unregistered model")
        TrustMark.check_and_download = local_only
        tm = TrustMark(verbose=False, model_type="Q", device="cpu", encoding_type=TrustMark.Encoding.BCH_4, loadRemover=False, loadBBoxDetector=False)

        def measure(path, expected, reference):
            image = Image.open(path)
            rgb = image.convert("RGB")
            other = Image.open(reference).convert("RGB")
            if rgb.size != other.size:
                raise ValueError("Dimensions changed")
            mse = math.fsum((a - b) ** 2 for a, b in zip(rgb.tobytes(), other.tobytes())) / len(rgb.tobytes())
            payload, detected, schema = tm.decode(rgb, MODE="binary", DETECTFIRST=False, ROTATION=False)
            raw = call([args.rust, "-m", args.models, "decode", "-i", path, "--variant", "Q"])
            return {"path": str(path.relative_to(HERE)), "bytes": path.stat().st_size, "sha256": sha(path), "rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(), "size": list(image.size), "alpha": "A" in image.getbands(), "mse_from_reference": mse, "psnr_from_reference": 10 * math.log10(255 ** 2 / mse) if mse else None, "python": {"payload": str(payload), "detected": bool(detected), "schema": int(schema), "exact": bool(detected) and schema == 2 and payload == expected}, "rust": {**raw, "exact": raw["returncode"] == 0 and raw["stdout"].strip() == "Found watermark: " + expected}}

        cases = json.loads((HERE / "cases.json").read_text())
        for case in cases:
            source = ROOT / case["source"]["path"]
            folder = output / case["id"]
            folder.mkdir()
            suffix = source.suffix
            control = {"id": case["id"], "states": {}, "errors": []}
            try:
                copy = folder / ("source" + suffix)
                copy.write_bytes(source.read_bytes())
                control["states"]["source"] = measure(copy, case["payload"], copy)
                removed = folder / ("source-removed" + suffix)
                require(call([args.rust, "-m", args.models, "remove", "-i", copy, "-o", removed, "--variant", "Q", "--quality", "95"]))
                control["states"]["removed"] = measure(removed, case["payload"], copy)
            except Exception as error:
                control["errors"].append(str(error))
            result["controls"].append(control)
            for encoder in ["python", "rust"]:
                trial = {"id": case["id"], "encoder": encoder, "expected_payload": case["payload"], "states": {}, "errors": []}
                try:
                    paths = {state: folder / (encoder + "-" + state + suffix) for state in ["marked", "signed", "cleaned", "removed"]}
                    if encoder == "python":
                        image = tm.encode(Image.open(source).convert("RGB"), case["payload"], MODE="binary", WM_STRENGTH=0.95, WM_MERGE="bilinear")
                        save_image(image, paths["marked"])
                    else:
                        trial["encoding"] = require(call([args.rust, "-m", args.models, "encode", "-i", source, "-o", paths["marked"], "--variant", "Q", "--version", "BCH_4", "--watermark", case["payload"], "--quality", "95"]))
                    trial["states"]["marked"] = measure(paths["marked"], case["payload"], source)
                    manifest = {"claim_generator": "declawd-trustmark-rust/1", "title": "Owned TrustMark comparison", "alg": "es256", "sign_cert": str(HERE / "test-cert.pem"), "private_key": str(args.key), "assertions": [{"label": "c2pa.actions", "data": {"actions": [{"action": "c2pa.created", "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/softwareImage"}]}}]}
                    manifest_path = folder / (encoder + "-manifest.json")
                    write_json(manifest_path, manifest)
                    trial["signing"] = require(call([args.c2patool, paths["marked"], "-m", manifest_path, "-o", paths["signed"]]))
                    trial["cleaning"] = require(call([args.declawd, "clean", "c2pa", paths["signed"], "--output", paths["cleaned"], "--json"]))
                    for state in ["signed", "cleaned"]:
                        trial["states"][state] = measure(paths[state], case["payload"], paths["marked"])
                        trial["states"][state]["oracle"] = call([args.c2patool, paths[state]])
                    trial["removal"] = require(call([args.rust, "-m", args.models, "remove", "-i", paths["marked"], "-o", paths["removed"], "--variant", "Q", "--quality", "95"]))
                    trial["states"]["removed"] = measure(paths["removed"], case["payload"], paths["marked"])
                    trial["cleaned_equals_marked"] = paths["cleaned"].read_bytes() == paths["marked"].read_bytes()
                except Exception as error:
                    trial["errors"].append(str(error))
                result["trials"].append(trial)
                write_json(output / "results.json", result)
                print(case["id"], encoder, {k: {d: v[d]["exact"] for d in ["python", "rust"]} for k, v in trial["states"].items()}, trial["errors"], flush=True)
    except Exception as error:
        result["errors"].append(str(error))
    write_json(output / "results.json", result)


if __name__ == "__main__":
    main()
