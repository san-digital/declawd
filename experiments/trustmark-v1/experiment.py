#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPSTREAM = "6df5a0a29b51cbec832695fdf02051a1937e37bd"
SEED = 20261029
IMAGE_SPECS = [
    ("gradient", 512, 512), ("tiles", 512, 512), ("noise", 512, 512),
    ("landscape", 768, 384), ("portrait", 384, 768), ("texture", 640, 480),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def file_record(path, base=HERE):
    data = path.read_bytes()
    return {"path": str(path.relative_to(base)), "bytes": len(data), "sha256": sha(data)}


def generated_image(name, width, height):
    from PIL import Image, ImageDraw
    if name == "noise":
        data = hashlib.shake_256(b"declawd.trustmark-v1/noise").digest(width * height * 3)
    else:
        data = bytearray()
        for y in range(height):
            for x in range(width):
                if name == "tiles":
                    value = ((x // 32) + (y // 32)) % 2
                    rgb = (40 + 180 * value, 160 - 80 * value, 80 + (x * y) % 80)
                elif name == "texture":
                    rgb = ((x * 3 + y) % 256, (x + y * 5) % 256, (x * y // 64) % 256)
                else:
                    rgb = (x * 255 // (width - 1), y * 255 // (height - 1), 128)
                data.extend(rgb)
    image = Image.frombytes("RGB", (width, height), bytes(data))
    draw = ImageDraw.Draw(image)
    if name == "landscape":
        draw.ellipse((550, 40, 650, 140), fill=(250, 220, 120))
        draw.polygon([(0, height), (0, 260), (220, 100), (470, 300), (650, 150), (width, 250), (width, height)], fill=(50, 95, 75))
    elif name == "portrait":
        for radius in range(140, 10, -20):
            draw.ellipse((width // 2 - radius, height // 2 - radius, width // 2 + radius, height // 2 + radius), fill=(40 + radius, 180 - radius, 100))
    return image


def save_image(image, path):
    if path.suffix == ".png":
        image.save(path, compress_level=9)
    else:
        image.save(path, quality=95, subsampling=0, optimize=False, progressive=False)


def prepare():
    if (HERE / "registration.json").exists():
        raise ValueError("registration already exists")
    cases = []
    for name, width, height in IMAGE_SPECS:
        image = generated_image(name, width, height)
        for extension in ("png", "jpg"):
            identifier = f"{name}-{extension}"
            folder = HERE / "assets" / identifier
            folder.mkdir(parents=True, exist_ok=False)
            source = folder / f"source.{extension}"
            save_image(image, source)
            payload = "".join(f"{byte:08b}" for byte in hashlib.sha256(identifier.encode()).digest())[:68]
            cases.append({"id": identifier, "size": [width, height], "payload": payload, "source": file_record(source)})
    registration = {
        "schema": "declawd.trustmark-registration/v1",
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "upstream_revision": UPSTREAM, "seed": SEED,
        "model": {"variant": "Q", "encoding": "BCH_4", "schema": 2, "payload_bits": 68, "strength": 1.0, "merge": "bilinear"},
        "execution": {"device": "cpu", "threads": 1, "rotation_search": False, "bounding_box_detector": False, "watermark_remover": False, "weights_only_load": True},
        "formats": {"png_compress_level": 9, "jpeg_quality": 95, "jpeg_subsampling": 0, "jpeg_optimize": False, "jpeg_progressive": False},
        "states": ["source", "marked", "signed", "cleaned"],
        "analysis": "Decode every state with the matching Q decoder. Record detection, payload and schema without dropping failures. Compare marked, signed and cleaned bytes and RGB pixels. Independently validate signed manifests and claim absence after cleaning. Count detections in the 12 unmarked controls without estimating a population false-positive rate.",
        "retries": "One encoding attempt per case. Retain every outcome. Setup or execution failures are recorded separately from watermark detection failures.",
        "scope": "Generated owned images, the selected Q model and fixed decoder settings. Results concern this set and do not measure SynthID, text watermarks or production vendor detectors.",
        "files": [file_record(HERE / name) for name in ("experiment.py", "models.json", "requirements-macos-arm64.lock", "runtime-wheels.json")],
        "cases": cases,
    }
    write_json(HERE / "registration.json", registration)
    print(f"registered {len(cases)} cases before inference")


def command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {arguments[0]}: {result.stderr}")
    return result.stdout


def load_models(source):
    if command(["git", "-C", str(source), "rev-parse", "HEAD"]).strip() != UPSTREAM:
        raise ValueError("unexpected TrustMark source revision")
    command(["git", "-C", str(source), "diff", "--exit-code", "HEAD", "--", "python"])
    models = json.loads((HERE / "models.json").read_text())
    hashes = {model["file"]: model["sha256"] for model in models}
    for model in models:
        path = source / "python/trustmark/models" / model["file"]
        if sha(path.read_bytes()) != model["sha256"]:
            raise ValueError(f"model hash mismatch: {model['file']}")
    os.environ["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
    sys.path.insert(0, str(source / "python"))
    import torch
    from trustmark import TrustMark
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    def cached_only(self, filename):
        path = Path(filename)
        if sha(path.read_bytes()) != hashes[path.name]:
            raise ValueError(f"model hash mismatch: {path.name}")
    TrustMark.check_and_download = cached_only
    return TrustMark(verbose=False, model_type="Q", device="cpu", encoding_type=TrustMark.Encoding.BCH_4, loadRemover=False, loadBBoxDetector=False)


def oracle(tool, path, output):
    result = subprocess.run([tool, str(path)], capture_output=True, text=True, timeout=120)
    write_json(output, {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    if result.returncode:
        if "No claim found" not in result.stderr:
            raise ValueError(f"unexpected C2PA oracle failure: {result.stderr}")
        return {"embedded_manifest": False, "binding": "no claim", "signature": "no claim", "credential": "no claim"}
    report = json.loads(result.stdout)
    label = report.get("active_manifest")
    if not label or label not in report.get("manifests", {}):
        raise ValueError("oracle reported no active manifest")
    active = report.get("validation_results", {}).get("activeManifest", {})
    success = {entry["code"] for entry in active.get("success", [])}
    failure = {entry["code"] for entry in active.get("failure", [])}
    return {"embedded_manifest": True,
            "binding": "mismatch" if "assertion.dataHash.mismatch" in failure else "match" if "assertion.dataHash.match" in success else "unavailable",
            "signature": "mismatch" if "claimSignature.mismatch" in failure else "validated" if "claimSignature.validated" in success else "unavailable",
            "credential": "untrusted" if "signingCredential.untrusted" in failure else "trusted" if "signingCredential.trusted" in success else "unavailable"}


def summary(cases):
    return {"cases": len(cases),
            "exact_payload_matches": {state: sum(case["states"][state]["decode"]["exact_payload"] for case in cases) for state in ("source", "marked", "signed", "cleaned")},
            "unmarked_detections": sum(case["states"]["source"]["decode"]["detected"] for case in cases),
            "byte_identical_after_removal": sum(case["relationships"]["cleaned_equals_marked"] for case in cases),
            "pixels_preserved_by_removal": sum(case["relationships"]["cleaned_pixels_equal_signed"] for case in cases)}


def run(source, output):
    from PIL import Image
    registration = json.loads((HERE / "registration.json").read_text())
    for record in registration["files"] + [case["source"] for case in registration["cases"]]:
        if sha((HERE / record["path"]).read_bytes()) != record["sha256"]:
            raise ValueError(f"registered file changed: {record['path']}")
    if output.exists():
        raise ValueError("use a new output directory to preserve earlier runs")
    registration_commit = command(["git", "-C", str(ROOT), "log", "-1", "--format=%H", "--", str(HERE / "registration.json")]).strip()
    if not registration_commit:
        raise ValueError("commit the registration before inference")
    tool = os.environ["C2PATOOL"]
    declawd = os.environ["DECLAWD_BIN"]
    if command([tool, "--version"]).strip() != "c2patool 0.27.12":
        raise ValueError("unexpected C2PA oracle version")
    tm = load_models(source)
    if tm.schemaCapacity() != 68:
        raise ValueError("unexpected TrustMark payload capacity")
    output.mkdir(parents=True)
    result = {"schema": "declawd.trustmark-results/v1", "started_at": datetime.now(timezone.utc).isoformat(),
              "registration_sha256": sha((HERE / "registration.json").read_bytes()), "registration_commit": registration_commit,
              "declawd_revision": command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip(),
              "declawd_binary_sha256": sha(Path(declawd).read_bytes()),
              "c2patool_version": "0.27.12", "c2patool_binary_sha256": sha(Path(tool).read_bytes()),
              "platform": {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine()},
              "runtime": {wheel["name"]: importlib.metadata.version(wheel["name"]) for wheel in json.loads((HERE / "runtime-wheels.json").read_text())["wheels"]},
              "cases": []}
    try:
        for case in registration["cases"]:
            folder = output / case["id"]
            folder.mkdir()
            extension = Path(case["source"]["path"]).suffix
            paths = {state: folder / f"{state}{extension}" for state in ("source", "marked", "signed", "cleaned")}
            paths["source"].write_bytes((HERE / case["source"]["path"]).read_bytes())
            cover = Image.open(paths["source"]).convert("RGB")
            marked = tm.encode(cover, case["payload"], MODE="binary", WM_STRENGTH=1.0, WM_MERGE="bilinear")
            save_image(marked, paths["marked"])
            manifest = {"claim_generator": "declawd-trustmark-experiment/1", "title": "Generated test image",
                        "assertions": [{"label": "c2pa.soft-binding", "data": {"alg": "com.adobe.trustmark.Q", "blocks": [{"scope": {}, "value": "2*" + case["payload"]}]}}]}
            write_json(folder / "signing-manifest.json", manifest)
            command([tool, str(paths["marked"]), "--manifest", str(folder / "signing-manifest.json"), "--output", str(paths["signed"])])
            cleaning = json.loads(command([declawd, "clean", "c2pa", str(paths["signed"]), "--output", str(paths["cleaned"]), "--json"]))
            write_json(folder / "clean-report.json", cleaning)
            states = {}
            for state, path in paths.items():
                image = Image.open(path).convert("RGB")
                payload, detected, schema = tm.decode(image, MODE="binary", DETECTFIRST=False, ROTATION=False)
                states[state] = {**file_record(path, output), "pixel_sha256": sha(image.tobytes()),
                                 "decode": {"payload": str(payload), "detected": bool(detected), "schema": int(schema), "exact_payload": bool(detected) and payload == case["payload"] and schema == 2},
                                 "c2pa": oracle(tool, path, folder / f"oracle-{state}.json")}
            row = {"id": case["id"], "expected_payload": case["payload"], "states": states,
                   "relationships": {"cleaned_equals_marked": paths["cleaned"].read_bytes() == paths["marked"].read_bytes(),
                                     "signed_pixels_equal_marked": states["signed"]["pixel_sha256"] == states["marked"]["pixel_sha256"],
                                     "cleaned_pixels_equal_signed": states["cleaned"]["pixel_sha256"] == states["signed"]["pixel_sha256"]},
                   "clean_verification": cleaning["verification"]}
            result["cases"].append(row)
            write_json(output / "results.json", result)
            print(case["id"], {state: states[state]["decode"]["exact_payload"] for state in states}, flush=True)
    except BaseException:
        result["execution_error"] = traceback.format_exc()
        write_json(output / "results.json", result)
        raise
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["summary"] = summary(result["cases"])
    result["files"] = [file_record(path, output) for path in sorted(output.rglob("*")) if path.is_file() and path.name != "results.json"]
    write_json(output / "results.json", result)
    print(json.dumps(result["summary"]))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("prepare")
    execute = commands.add_parser("run")
    execute.add_argument("--source", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare()
    else:
        run(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
