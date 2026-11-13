from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
INPUTS = ["PLAN.md", "study.py", "test_study.py"]
SEED = 20261113
ALPHA = 0.05


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_bound(logs, threshold):
    residual = math.fsum(logs)
    result = 0
    for value in sorted((max(0.0, item) for item in logs), reverse=True):
        if residual <= threshold:
            break
        result += 1
        residual -= value
    return result


def weighted_ebh(log_evalues, lengths, alpha):
    order = sorted(range(len(lengths)), key=lambda i: (-log_evalues[i], i))
    mass = 0
    selected = 0
    for rank, index in enumerate(order, 1):
        mass += lengths[index]
        if log_evalues[index] >= math.log(sum(lengths) / (alpha * mass)):
            selected = rank
    return sorted(order[:selected])


def lower_bound(positives, size, null_upper):
    margin = math.sqrt(math.log(2 / ALPHA) / (2 * size))
    return max(0.0, (positives / size - margin - null_upper) / (1 - null_upper))


def generate():
    rng = random.Random(SEED)
    documents = []
    for condition in ["uniform", "central_marked", "repeated_invalid_null"]:
        for replicate in range(100):
            if condition == "repeated_invalid_null":
                pivots = [rng.random()] * 64
            else:
                pivots = [rng.random() for _ in range(64)]
            labels = [condition == "central_marked" and 16 <= i < 48 for i in range(64)]
            pivots = [max(sys.float_info.min, p ** 3 if label else p) for p, label in zip(pivots, labels)]
            logs = [-math.log(2) - 0.5 * math.log(p) for p in pivots]
            intervals = []
            for start in range(64):
                for end in range(start + 1, 65):
                    bound = count_bound(logs[start:end], math.log(64 / ALPHA))
                    truth = sum(labels[start:end])
                    intervals.append([start, end, bound, truth])
            blocks = [math.fsum(logs[i:i + 16]) for i in range(0, 64, 16)]
            rejected = weighted_ebh(blocks, [16] * 4, ALPHA)
            false_tokens = sum(16 - sum(labels[i * 16:(i + 1) * 16]) for i in rejected)
            documents.append({"condition": condition, "replicate": replicate, "pivots": pivots, "labels": labels, "intervals": intervals, "count_overclaim": any(row[2] > row[3] for row in intervals), "count_detected": any(row[2] > 0 for row in intervals), "block_log_evalues": blocks, "rejected_blocks": rejected, "false_tokens": false_tokens, "token_fdp": false_tokens / (16 * len(rejected)) if rejected else 0.0})
    prevalence = []
    for null_rate in [0.05, 0.06]:
        for size in [2000, 100000]:
            for replicate in range(10):
                calibration = sum(rng.random() < null_rate for _ in range(20000))
                positives = sum(rng.random() < null_rate for _ in range(size))
                upper = min(0.999999, calibration / 20000 + math.sqrt(math.log(2 / ALPHA) / 40000))
                prevalence.append({"null_rate": null_rate, "size": size, "replicate": replicate, "calibration_size": 20000, "calibration_positives": calibration, "positives": positives, "true_origin_share": 0, "exact_null_lower": lower_bound(positives, size, 0.05), "calibrated_null_upper": upper, "calibrated_lower": lower_bound(positives, size, upper)})
    summary = []
    for condition in ["uniform", "central_marked", "repeated_invalid_null"]:
        rows = [row for row in documents if row["condition"] == condition]
        summary.append({"condition": condition, "documents": len(rows), "count_overclaim_documents": sum(row["count_overclaim"] for row in rows), "count_detection_documents": sum(row["count_detected"] for row in rows), "mean_token_fdp": math.fsum(row["token_fdp"] for row in rows) / len(rows)})
    return {"schema": "declawd.text-null-study/v1", "seed": SEED, "alpha": ALPHA, "summary": summary, "documents": documents, "prevalence": prevalence}


def verify_registration():
    registration = json.loads((ROOT / "registration.json").read_text())
    if registration["inputs"] != {name: sha(ROOT / name) for name in INPUTS} or registration["seed"] != SEED:
        raise ValueError("Registered inputs or seed differ")
    subprocess.run(["git", "merge-base", "--is-ancestor", registration["input_commit"], "HEAD"], cwd=ROOT, check=True)
    for name in INPUTS:
        original = subprocess.check_output(["git", "show", registration["input_commit"] + ":experiments/text-null-v1/" + name], cwd=ROOT)
        if hashlib.sha256(original).hexdigest() != registration["inputs"][name]:
            raise ValueError("Input commit differs")
    return registration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["register", "run", "verify"])
    args = parser.parse_args()
    if args.action == "register":
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        registration = {"schema": "declawd.text-null-registration/v1", "input_commit": commit, "seed": SEED, "inputs": {name: sha(ROOT / name) for name in INPUTS}}
        with (ROOT / "registration.json").open("xb") as stream:
            stream.write(encoded(registration))
        verify_registration()
        return
    registration = verify_registration()
    subprocess.run(["git", "ls-files", "--error-unmatch", "registration.json"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    committed = subprocess.check_output(["git", "show", "HEAD:experiments/text-null-v1/registration.json"], cwd=ROOT)
    if committed != encoded(registration):
        raise ValueError("Registration must be committed before generation")
    result = generate()
    result["registration_sha256"] = sha(ROOT / "registration.json")
    result["python"] = sys.version.split()[0]
    if args.action == "run":
        with (ROOT / "results.json").open("xb") as stream:
            stream.write(encoded(result))
    else:
        expected = json.loads((ROOT / "results.json").read_text())
        result["python"] = expected["python"]
        if encoded(result) != encoded(expected):
            raise ValueError("Recomputed outcomes differ")
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
