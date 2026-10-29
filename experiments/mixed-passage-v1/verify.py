#!/usr/bin/env python3
"""Audit the recorded counts independently of the registered scoring functions."""

from collections import Counter
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG = json.loads((HERE / "config.json").read_bytes())
KEY = bytes.fromhex(json.loads((HERE / "seed.json").read_bytes())["key_hex"])
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prefix(text, length):
    return text[:list(WORD.finditer(text))[length - 1].end()]


@lru_cache(maxsize=200_000)
def green(pair):
    message = CONFIG["domain"].encode() + KEY
    for word in pair:
        raw = word.encode()
        message += len(raw).to_bytes(4, "big") + raw
    return hashlib.sha256(message).digest()[7] & 3 == 0


def score(words):
    pairs = set(zip(words[:-1], words[1:]))
    return {"g": sum(map(green, pairs)), "n": len(pairs)}


def rank(row):
    numerator = 4 * row["g"] - row["n"]
    square = Fraction(numerator ** 2, 3 * row["n"])
    return (1 if numerator >= 0 else -1, square if numerator >= 0 else -square, -row["start"], row["start"] - row["end"])


def crossing(row, threshold):
    if row is None or row["n"] < CONFIG["minimum_pairs"]:
        return False
    numerator = 4 * row["g"] - row["n"]
    return numerator > 0 and Fraction(numerator ** 2, 3 * row["n"]) > Fraction(threshold, 100) ** 2


def document(row, backgrounds, generated):
    original = prefix(backgrounds[row["id"].split("/")[0]]["text"], row["background_tokens"])
    if row.get("condition", "human") == "human":
        return original
    passage = prefix(generated[row["condition"]], row["insertion_tokens"])
    words = list(WORD.finditer(original))
    point = {"start": 0, "middle": len(words) // 2, "end": len(words)}[row["position"]]
    offset = words[point].start() if point < len(words) else len(original)
    assert row["insertion_span"] == [point, point + row["insertion_tokens"]]
    return (original[:offset].rstrip() + "\n\n" + passage + "\n\n" + original[offset:].lstrip()).strip()


def audit_report(report, trace_path, backgrounds, generated):
    traces = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert len(traces) == len(report["rows"])
    windows = 0
    for row, trace in zip(report["rows"], traces):
        assert row["id"] == trace["id"]
        text = document(row, backgrounds, generated)
        words = [m.group().lower() for m in WORD.finditer(text)]
        assert row["text_sha256"] == sha(text.encode())
        assert row["tokens"] == len(words)
        assert row["whole"] == score(words), row["id"]
        expected = []
        for width in CONFIG["window_tokens"]:
            if width <= len(words):
                starts = list(range(0, len(words) - width + 1, CONFIG["stride"]))
                if starts[-1] != len(words) - width:
                    starts.append(len(words) - width)
                for start in starts:
                    expected.append({"start": start, "end": start + width, **score(words[start:start + width])})
        assert trace["windows"] == expected, row["id"]
        eligible = [r for r in expected if r["n"] >= CONFIG["minimum_pairs"]]
        assert row["window"] == (max(eligible, key=rank) if eligible else None), row["id"]
        assert row["windows"] == len(expected)
        assert row["eligible_windows"] == len(eligible)
        assert row["trace_sha256"] == sha((json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
        windows += len(expected)
    return windows


def audit_provenance():
    provenance = read(HERE / "provenance.json")
    for output in provenance["outputs"]:
        data = (HERE / output["path"]).read_bytes()
        assert len(data) == output["bytes"] and sha(data) == output["sha256"], output["path"]
    commits = provenance["commits"]
    registration = read(HERE / "registration.json")
    assert read(HERE / "seed.json")["registration_commit"] == commits["registration"]
    for earlier, later in [(provenance["source_base_commit"], commits["registration"]), (commits["registration"], commits["key"]), (commits["key"], commits["calibration"])]:
        subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", earlier, later], check=True)
    files = [(commits["registration"], path) for path in registration["files"]]
    files += [(commits["registration"], str((HERE / "registration.json").relative_to(ROOT))), (commits["key"], str((HERE / "seed.json").relative_to(ROOT)))]
    files += [(commits["calibration"], str((HERE / path).relative_to(ROOT))) for path in ["calibration/report.json", "calibration/windows.jsonl"]]
    for commit, path in files:
        assert subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{path}"]) == (ROOT / path).read_bytes(), path


def main():
    audit_provenance()
    backgrounds = {r["id"]: r for r in read(HERE / "corpus.json")["backgrounds"]}
    calibration = read(HERE / "calibration/report.json")
    evaluation = read(HERE / "run/evaluation.json")
    windows = audit_report(calibration, HERE / "calibration/windows.jsonl", backgrounds, {})
    windows += audit_report(evaluation, HERE / "run/windows.jsonl", backgrounds, evaluation["generated"])
    thresholds = calibration["thresholds_hundredths"]
    for method, chosen in thresholds.items():
        for candidate in range(0, chosen + 1, CONFIG["threshold_step_hundredths"]):
            passed = []
            for length in CONFIG["background_tokens"]:
                group = [r for r in calibration["rows"] if r["background_tokens"] == length]
                passed.append(Fraction(sum(crossing(r[method], candidate) for r in group), len(group)) <= Fraction(**CONFIG["false_positive_target"]))
            assert all(passed) == (candidate == chosen)
    conditions = Counter()
    for row in evaluation["rows"]:
        conditions[row["condition"]] += 1
        for method in ["whole", "window", "uncorrected_window"]:
            threshold = thresholds["whole" if method == "uncorrected_window" else method]
            source = "window" if method == "uncorrected_window" else method
            assert row["detected"][method] == crossing(row[source], threshold)
        if "localisation" in row:
            a, b = row["insertion_span"]
            window = row["window"]
            overlap = max(0, min(b, window["end"]) - max(a, window["start"]))
            union = b - a + window["end"] - window["start"] - overlap
            assert row["localisation"] == {"intersection_tokens": overlap, "union_tokens": union, "insertion_covered": overlap / (b - a), "iou": overlap / union, "localised_detection": row["detected"]["window"] and Fraction(overlap, union) >= Fraction(1, 2)}
    assert conditions == {"human": 72, "marked": 648, "neutral": 648}
    for summary in evaluation["summary"]:
        group = [r for r in evaluation["rows"] if all(r[k] == summary[k] for k in ["condition", "background_tokens", "insertion_tokens"]) and (summary["position"] == "all" or r["position"] == summary["position"])]
        assert summary["documents"] == len(group)
        for method in ["whole", "window", "uncorrected_window"]:
            assert summary[method] == sum(r["detected"][method] for r in group)
        assert summary["localised_detections"] == sum(r.get("localisation", {}).get("localised_detection", False) for r in group)
    print(f"Independently verified {windows} windows, document counts, exact thresholds, verdicts, locations and the committed input sequence")


if __name__ == "__main__":
    main()
