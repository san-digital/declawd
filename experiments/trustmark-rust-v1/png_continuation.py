from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from experiment import HERE, ROOT, call, registration, sha, write_json


def remove_arguments(binary, models, source, output):
    if Path(source).suffix != ".png" or Path(output).suffix != ".png":
        raise ValueError("The continuation accepts PNG only")
    return [binary, "-m", models, "remove", "-i", source, "-o", output, "--variant", "Q"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--rust", type=Path, required=True)
    args = parser.parse_args()
    registration()
    receipt = json.loads((HERE / "png-registration.json").read_text())
    subprocess.run(["git", "merge-base", "--is-ancestor", receipt["input_commit"], "HEAD"], cwd=ROOT, check=True)
    for name, digest in receipt["files"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Continuation input differs: " + name)
        original = subprocess.check_output(["git", "show", receipt["input_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(original).hexdigest() != digest:
            raise ValueError("Continuation input commit differs")
    if subprocess.check_output(["git", "show", "HEAD:experiments/trustmark-rust-v1/png-registration.json"], cwd=ROOT) != (HERE / "png-registration.json").read_bytes():
        raise ValueError("Commit continuation registration before inference")
    runtime = json.loads((HERE / "runtime.json").read_text())
    if sha(args.rust) != runtime["binaries"]["rust"]:
        raise ValueError("Rust binary differs")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.source, text=True).strip() != runtime["upstream_revision"]:
        raise ValueError("Upstream revision differs")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "python"], cwd=args.source, check=True)
    models = json.loads((HERE / "models.json").read_text())
    hashes = {item["name"]: item["sha256"] for item in models}
    for item in models:
        directory = args.models if item["name"].endswith(".onnx") else args.source / "python/trustmark/models"
        if sha(directory / item["name"]) != item["sha256"]:
            raise ValueError("Model differs")
    with (HERE / "png-attempt.json").open("x") as stream:
        json.dump({"started_at": datetime.now(timezone.utc).isoformat(), "registration_sha256": sha(HERE / "png-registration.json")}, stream, indent=2)
    output = HERE / "png-removal"
    output.mkdir()
    result = {"schema": "declawd.trustmark-png-continuation/v1", "registration_sha256": sha(HERE / "png-registration.json"), "cases": [], "errors": []}
    try:
        os.environ["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
        sys.path.insert(0, str(args.source / "python"))
        import torch
        from PIL import Image
        from trustmark import TrustMark
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.manual_seed(20261113)
        torch.use_deterministic_algorithms(True)

        def local_only(self, filename):
            if sha(Path(filename)) != hashes[Path(filename).name]:
                raise ValueError("Unregistered model")
        TrustMark.check_and_download = local_only
        tm = TrustMark(verbose=False, model_type="Q", device="cpu", encoding_type=TrustMark.Encoding.BCH_4, loadRemover=False, loadBBoxDetector=False)
        for case in json.loads((HERE / "png-inputs.json").read_text()):
            row = {**case, "errors": []}
            try:
                source = ROOT / case["path"]
                target = output / (case["id"] + "-" + case["encoder"] + ".png")
                row["removal"] = call(remove_arguments(args.rust, args.models, source, target))
                if row["removal"]["returncode"]:
                    raise ValueError(row["removal"])
                image = Image.open(target)
                rgb = image.convert("RGB")
                original = Image.open(source).convert("RGB")
                if image.size != original.size:
                    raise ValueError("Dimensions changed")
                payload, detected, schema = tm.decode(rgb, MODE="binary", DETECTFIRST=False, ROTATION=False)
                decoded = call([args.rust, "-m", args.models, "decode", "-i", target, "--variant", "Q"])
                mse = math.fsum((a - b) ** 2 for a, b in zip(rgb.tobytes(), original.tobytes())) / len(rgb.tobytes())
                row.update(output=str(target.relative_to(HERE)), output_sha256=sha(target), bytes=target.stat().st_size, rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(), size=list(image.size), alpha="A" in image.getbands(), mse=mse, psnr=10 * math.log10(255 ** 2 / mse) if mse else None, python={"payload": str(payload), "detected": bool(detected), "schema": int(schema), "exact": bool(detected) and schema == 2 and payload == case["expected_payload"]}, rust={**decoded, "exact": decoded["returncode"] == 0 and decoded["stdout"].strip() == "Found watermark: " + case["expected_payload"]})
            except Exception as error:
                row["errors"].append(str(error))
            result["cases"].append(row)
            write_json(output / "results.json", result)
            print(case["id"], case["encoder"], row.get("python", {}).get("exact"), row.get("rust", {}).get("exact"), row["errors"], flush=True)
    except Exception as error:
        result["errors"].append(str(error))
    write_json(output / "results.json", result)


if __name__ == "__main__":
    main()
