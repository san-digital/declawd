#!/usr/bin/env python3
"""Run the registered mixed-passage experiment using the Python standard library."""

from __future__ import annotations

import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import subprocess
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
CONFIG = json.loads((HERE / "config.json").read_text())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value, exclusive=False):
    with path.open("xb" if exclusive else "wb") as stream:
        stream.write(encoded(value))


def load(path):
    return json.loads(path.read_bytes())


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def tokens(text):
    return [m.group().lower() for m in TOKEN.finditer(text)]


def prefix(text, count):
    matches = list(TOKEN.finditer(text))
    if len(matches) < count:
        raise ValueError(f"Requested {count} tokens from {len(matches)} tokens")
    return text[:matches[count - 1].end()]


@lru_cache(maxsize=200_000)
def green(previous, current, key):
    a, b = previous.encode(), current.encode()
    data = CONFIG["domain"].encode() + key + len(a).to_bytes(4, "big") + a + len(b).to_bytes(4, "big") + b
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big") % 4 == 0


def counts(words, key):
    pairs = set(zip(words, words[1:]))
    return {"n": len(pairs), "g": sum(green(a, b, key) for a, b in pairs)}


def z(score):
    return (4 * score["g"] - score["n"]) / math.sqrt(3 * score["n"]) if score["n"] else None


def crosses(score, hundredths):
    if score is None or score["n"] < CONFIG["minimum_pairs"]:
        return False
    numerator = 4 * score["g"] - score["n"]
    return numerator > 0 and numerator * numerator * 10_000 > hundredths * hundredths * 3 * score["n"]


def better(candidate, best):
    if best is None:
        return True
    a, b = 4 * candidate["g"] - candidate["n"], 4 * best["g"] - best["n"]
    if (a >= 0) != (b >= 0):
        return a >= 0
    comparison = a * a * best["n"] - b * b * candidate["n"]
    if comparison:
        return comparison > 0 if a >= 0 else comparison < 0
    return (candidate["start"], candidate["end"] - candidate["start"]) < (best["start"], best["end"] - best["start"])


def search(words, key):
    trace, best = [], None
    for width in CONFIG["window_tokens"]:
        if width > len(words):
            continue
        starts = sorted(set(range(0, len(words) - width + 1, CONFIG["stride"])) | {len(words) - width})
        for start in starts:
            row = {"start": start, "end": start + width, **counts(words[start:start + width], key)}
            trace.append(row)
            if row["n"] >= CONFIG["minimum_pairs"] and better(row, best):
                best = row
    return best, trace


def analyse(text, key):
    words = tokens(text)
    whole = counts(words, key)
    window, trace = search(words, key)
    return {"text_sha256": digest(text.encode()), "tokens": len(words), "whole": whole, "window": window, "windows": len(trace), "eligible_windows": sum(r["n"] >= CONFIG["minimum_pairs"] for r in trace), "trace_sha256": digest(encoded(trace))}, trace


def generate(key, marked):
    parts, previous = [], ""
    for segment in load(ROOT / CONFIG["sources"]["template"])["segments"]:
        if isinstance(segment, str):
            parts.append(segment)
            scanned = tokens(segment)
            if scanned:
                previous = scanned[-1]
        else:
            if not segment or any(TOKEN.fullmatch(s) is None for s in segment):
                raise ValueError("Template candidates must be single ASCII tokens")
            chosen = next((s for s in segment if green(previous, s.lower(), key)), segment[0]) if marked else segment[0]
            parts.append(chosen)
            previous = chosen.lower()
    return "".join(parts)


def insert(background, passage, position):
    matches = list(TOKEN.finditer(background))
    index = {"start": 0, "middle": len(matches) // 2, "end": len(matches)}[position]
    offset = matches[index].start() if index < len(matches) else len(background)
    text = background[:offset].rstrip() + "\n\n" + passage + "\n\n" + background[offset:].lstrip()
    return text.strip(), [index, index + len(tokens(passage))]


def prepare():
    source = load(ROOT / CONFIG["sources"]["corpus"])
    authors = defaultdict(list)
    for passage in source["passages"]:
        authors[passage["author"]].append(passage)
    backgrounds = []
    for author, passages in sorted(authors.items()):
        if len(passages) != 12 or len({p["split"] for p in passages}) != 1:
            raise ValueError("Expected twelve passages and one split per author")
        for start in range(0, len(passages), CONFIG["source_passages_per_background"]):
            group = passages[start:start + CONFIG["source_passages_per_background"]]
            text = prefix("\n\n".join(p["text"] for p in group), max(CONFIG["background_tokens"]))
            backgrounds.append({"id": f"pg{group[0]['gutenberg_id']}-{start // 4}", "author": author, "title": group[0]["title"], "split": group[0]["split"], "sources": [p["id"] for p in group], "text": text})
    write(HERE / "corpus.json", {"licence": source["licence"], "reuse": "Derived from the historical v1/v2 corpus. Three disjoint groups per author, with overlapping prefixes within each group.", "backgrounds": backgrounds}, exclusive=True)
    paths = [HERE / p for p in ["PLAN.md", "config.json", "corpus.json", "experiment.py", "test_experiment.py"]]
    paths += [ROOT / path for path in CONFIG["sources"].values()]
    registration = {"schema": "declawd.mixed-passage-registration/v1", "experiment_id": CONFIG["experiment_id"], "registered_at": datetime.now(timezone.utc).isoformat(), "config": CONFIG, "files": {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}}
    write(HERE / "registration.json", registration, exclusive=True)
    print(f"Registered {len(backgrounds)} human backgrounds. Commit the registration before drawing the key.")


def verify_inputs():
    registration = load(HERE / "registration.json")
    if registration["config"] != CONFIG or registration["experiment_id"] != CONFIG["experiment_id"]:
        raise ValueError("Registration configuration differs")
    for path, expected in registration["files"].items():
        if Path(path).is_absolute() or ".." in Path(path).parts or digest((ROOT / path).read_bytes()) != expected:
            raise ValueError(f"Registered input differs: {path}")
    return registration


def committed(path):
    relative = str(path.relative_to(ROOT))
    if subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{relative}"]) != path.read_bytes():
        raise ValueError(f"Commit the frozen file first: {relative}")


def draw():
    verify_inputs()
    registration = HERE / "registration.json"
    committed(registration)
    for path in load(registration)["files"]:
        committed(ROOT / path)
    with (HERE / "seed.json").open("xb") as stream:
        record = {"schema": "declawd.mixed-passage-seed/v1", "key_hex": secrets.token_bytes(32).hex(), "drawn_at": datetime.now(timezone.utc).isoformat(), "registration_sha256": digest(registration.read_bytes()), "registration_commit": git("log", "-1", "--format=%H", "--", str(registration.relative_to(ROOT)))}
        stream.write(encoded(record))
    print("Recorded one public key. Commit and push seed.json before calibration.")


def context(require_commits=False):
    verify_inputs()
    seed = load(HERE / "seed.json")
    if seed["registration_sha256"] != digest((HERE / "registration.json").read_bytes()):
        raise ValueError("Seed is bound to a different registration")
    if require_commits:
        committed(HERE / "seed.json")
    key = bytes.fromhex(seed["key_hex"])
    if len(key) != 32:
        raise ValueError("Expected a 32-byte key")
    backgrounds = load(HERE / "corpus.json")["backgrounds"]
    return key, backgrounds


def threshold(rows, method):
    target = CONFIG["false_positive_target"]
    for step in range(CONFIG["threshold_steps"]):
        value = step * CONFIG["threshold_step_hundredths"]
        groups = [[r for r in rows if r["background_tokens"] == length] for length in CONFIG["background_tokens"]]
        if all(group and sum(crosses(r[method], value) for r in group) * target["denominator"] <= len(group) * target["numerator"] for group in groups):
            return value
    raise ValueError("No registered threshold meets the calibration rule")


def calibrate_data(key, backgrounds):
    rows, traces = [], []
    for background in backgrounds:
        if background["split"] != "calibration":
            continue
        for length in CONFIG["background_tokens"]:
            case_id = f"{background['id']}/human/{length}"
            result, trace = analyse(prefix(background["text"], length), key)
            if result["whole"]["n"] < CONFIG["minimum_pairs"] or result["window"] is None:
                raise ValueError(f"Unavailable calibration score: {case_id}")
            rows.append({"id": case_id, "author": background["author"], "background_tokens": length, **result})
            traces.append({"id": case_id, "windows": trace})
    return {"schema": "declawd.mixed-passage-calibration/v1", "registration_sha256": digest((HERE / "registration.json").read_bytes()), "seed_sha256": digest((HERE / "seed.json").read_bytes()), "thresholds_hundredths": {method: threshold(rows, method) for method in ["whole", "window"]}, "rows": rows}, traces


def verdicts(row, thresholds):
    return {"whole": crosses(row["whole"], thresholds["whole"]), "window": crosses(row["window"], thresholds["window"]), "uncorrected_window": crosses(row["window"], thresholds["whole"])}


def evaluate_data(key, backgrounds, calibration):
    thresholds = calibration["thresholds_hundredths"]
    generated = {condition: generate(key, condition == "marked") for condition in ["marked", "neutral"]}
    rows, traces = [], []
    for background in backgrounds:
        if background["split"] != "evaluation":
            continue
        for length in CONFIG["background_tokens"]:
            human = prefix(background["text"], length)
            cases = [("human", 0, "none", human, None)]
            for condition, passage in generated.items():
                for insertion_length in CONFIG["insertion_tokens"]:
                    for position in CONFIG["positions"]:
                        text, span = insert(human, prefix(passage, insertion_length), position)
                        cases.append((condition, insertion_length, position, text, span))
            for condition, insertion_length, position, text, span in cases:
                case_id = f"{background['id']}/{condition}/{length}/{insertion_length}/{position}"
                result, trace = analyse(text, key)
                row = {"id": case_id, "author": background["author"], "condition": condition, "background_tokens": length, "insertion_tokens": insertion_length, "position": position, "insertion_span": span, **result}
                row["detected"] = verdicts(row, thresholds)
                if span and row["window"]:
                    window = row["window"]
                    intersection = max(0, min(span[1], window["end"]) - max(span[0], window["start"]))
                    union = span[1] - span[0] + window["end"] - window["start"] - intersection
                    row["localisation"] = {"intersection_tokens": intersection, "union_tokens": union, "insertion_covered": intersection / insertion_length, "iou": intersection / union, "localised_detection": row["detected"]["window"] and intersection * 2 >= union}
                rows.append(row)
                traces.append({"id": case_id, "windows": trace})
    summary = summarise(rows)
    isolated = {condition: [{"tokens": length, **counts(tokens(prefix(text, length)), key), "text_sha256": digest(prefix(text, length).encode())} for length in CONFIG["insertion_tokens"]] for condition, text in generated.items()}
    return {"schema": "declawd.mixed-passage-evaluation/v1", "calibration_sha256": digest(encoded(calibration)), "generated": generated, "isolated": isolated, "summary": summary, "rows": rows}, traces


def summarise(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["background_tokens"], row["insertion_tokens"], "all")].append(row)
        groups[(row["condition"], row["background_tokens"], row["insertion_tokens"], row["position"])].append(row)
    result = []
    for (condition, length, inserted, position), group in sorted(groups.items()):
        by_author = {}
        for author in sorted({r["author"] for r in group}):
            author_rows = [r for r in group if r["author"] == author]
            by_author[author] = {"documents": len(author_rows), **{m: sum(r["detected"][m] for r in author_rows) for m in ["whole", "window", "uncorrected_window"]}}
        result.append({"condition": condition, "background_tokens": length, "insertion_tokens": inserted, "position": position, "documents": len(group), **{m: sum(r["detected"][m] for r in group) for m in ["whole", "window", "uncorrected_window"]}, "unavailable_whole": sum(r["whole"]["n"] < CONFIG["minimum_pairs"] for r in group), "unavailable_window": sum(r["window"] is None for r in group), "localised_detections": sum(r.get("localisation", {}).get("localised_detection", False) for r in group), "by_author": by_author})
    return result


def trace_bytes(traces):
    return b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in traces)


def run_calibration():
    key, backgrounds = context(require_commits=True)
    output = HERE / "calibration"
    output.mkdir()
    try:
        report, traces = calibrate_data(key, backgrounds)
        write(output / "report.json", report, exclusive=True)
        (output / "windows.jsonl").write_bytes(trace_bytes(traces))
        print(json.dumps(report["thresholds_hundredths"]))
    except Exception as error:
        write(output / "error.json", {"error": str(error)})
        raise


def run_evaluation():
    key, backgrounds = context(require_commits=True)
    path = HERE / "calibration/report.json"
    committed(path)
    committed(HERE / "calibration/windows.jsonl")
    expected, traces = calibrate_data(key, backgrounds)
    if path.read_bytes() != encoded(expected):
        raise ValueError("Calibration differs from its registered inputs")
    if (HERE / "calibration/windows.jsonl").read_bytes() != trace_bytes(traces):
        raise ValueError("Calibration search traces differ")
    output = HERE / "run"
    output.mkdir()
    try:
        report, traces = evaluate_data(key, backgrounds, expected)
        write(output / "evaluation.json", report, exclusive=True)
        (output / "windows.jsonl").write_bytes(trace_bytes(traces))
        for condition, text in report["generated"].items():
            (output / f"{condition}.txt").write_text(text + "\n")
        print(f"Recorded {len(report['rows'])} evaluation cases")
    except Exception as error:
        write(output / "error.json", {"error": str(error)})
        raise


def verify():
    key, backgrounds = context()
    calibration, calibration_traces = calibrate_data(key, backgrounds)
    evaluation, evaluation_traces = evaluate_data(key, backgrounds, calibration)
    outputs = {"calibration/report.json": encoded(calibration), "calibration/windows.jsonl": trace_bytes(calibration_traces), "run/evaluation.json": encoded(evaluation), "run/windows.jsonl": trace_bytes(evaluation_traces)}
    outputs.update({f"run/{condition}.txt": (text + "\n").encode() for condition, text in evaluation["generated"].items()})
    for path, expected in outputs.items():
        if (HERE / path).read_bytes() != expected:
            raise ValueError(f"Frozen output differs: {path}")
    print(f"Verified {len(calibration['rows'])} calibration cases and {len(evaluation['rows'])} evaluation cases, including every window")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "draw", "calibrate", "evaluate", "verify"])
    args = parser.parse_args()
    {"prepare": prepare, "draw": draw, "calibrate": run_calibration, "evaluate": run_evaluation, "verify": verify}[args.command]()
