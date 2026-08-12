#!/usr/bin/env python3
"""Run the frozen calibration sequence: register, sample one seed, calibrate, evaluate.

Everything that could be tuned after seeing a score is committed first and
hashed: the passage template and candidate tables, both corpora, the bundled
rewrite, the exact perturbation targets, and both targets for the detector.
Only then is a seed sampled. The threshold is chosen on the calibration corpus
alone, and the evaluation corpus is scored afterwards in a single pass.

Two honest limits on that. Recording a sampled seed does not prove to a reader
that it was the first value drawn, so this is a documented no-reroll process
rather than a cryptographically non-adaptive one. And re-running this script
re-scores the evaluation corpus: the published figures are those of the
committed run, which is what the reports record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

import declawd  # noqa: E402

REGISTRATION = ROOT / "fixtures" / "registration-v1.json"
PROFILE = ROOT / "fixtures" / "profile-v1.json"
CALIBRATION_REPORT = ROOT / "reports" / "calibration-report-v1.json"
EVALUATION_REPORT = ROOT / "reports" / "evaluation-report-v1.json"

# Declared before any score is seen. Raising these afterwards would make the
# whole exercise decorative.
FALSE_POSITIVE_TARGET = 0.02
MIN_EFFECTIVE_TOKENS = 120


def digest(path: Path) -> str:
    """SHA-256 over the exact committed bytes. No parse, no reserialise."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Assumes the passage verdicts are meaningfully independent."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def z_of(text: str) -> tuple[float, int]:
    result = declawd.score(text)
    return (result.z_display or 0.0, result.effective_tokens)


def load_corpus(split: str) -> list[dict]:
    data = json.loads((ROOT / "fixtures" / "corpus.json").read_text(encoding="utf-8"))
    return [p for p in data["passages"] if p["split"] == split]


def register(template: Path, corpus: Path) -> dict:
    """Commit every score-affecting input before a seed exists.

    That includes the bundled rewrite and the exact perturbation targets. Both
    were previously authored or edited after calibration, which meant the claim
    that everything tunable was frozen first was not true of them.
    """
    payload = {
        "registration_id": "declawd-v1",
        "targets": {
            "false_positive_rate_at_or_below": FALSE_POSITIVE_TARGET,
            "marked_fixture_must_be_detected": True,
            "min_effective_tokens": MIN_EFFECTIVE_TOKENS,
        },
        "tokeniser": {"pattern": declawd.TOKEN_PATTERN.pattern, "folding": "ASCII A-Z to a-z"},
        "gamma": {"numerator": declawd.GAMMA_NUM, "denominator": declawd.GAMMA_DEN},
        "domain_separator": declawd.DOMAIN_SEPARATOR.decode("ascii"),
        "template_sha256": digest(template),
        "corpus_sha256": digest(corpus),
        "rewrite_sha256": digest(ROOT / "fixtures" / "rewrite.json"),
        "perturbations_sha256": digest(ROOT / "fixtures" / "perturbations.json"),
        "canonicaliser": {
            "zero_width": "U+200B",
            "confusables": declawd.CONFUSABLES,
        },
        "perturbations": json.loads(
            (ROOT / "fixtures" / "perturbations.json").read_text(encoding="utf-8"))["targets"],
        "analysis": {
            "unit": "one verdict per passage",
            "interval": "Wilson, 95 per cent",
            "corpus_split": "by author; no evaluation author appears in calibration",
            "selection": "all results reported; no example selected",
        },
        "note": "Committed before the seed was sampled. Targets are not revised after scoring.",
    }
    write_json(REGISTRATION, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-hex",
                        help="reproduce the committed run; must match the committed profile")
    args = parser.parse_args()

    template_path = ROOT / "fixtures" / "template.json"
    corpus_path = ROOT / "fixtures" / "corpus.json"

    previous = None
    if args.seed_hex and CALIBRATION_REPORT.exists():
        previous = json.loads(CALIBRATION_REPORT.read_text(encoding="utf-8"))

    register(template_path, corpus_path)
    registration_sha = digest(REGISTRATION)
    print(f"[ok] registration committed  {registration_sha[:16]}")

    # --seed-hex reproduces the committed run and nothing else. Allowing an
    # arbitrary seed here would be the grinding vector the whole procedure
    # exists to prevent: try seeds until one flatters the demonstration.
    if args.seed_hex:
        if not previous:
            print("[failed] --seed-hex reproduces a committed run, but no calibration "
                  "report exists to reproduce.", file=sys.stderr)
            return 1
        if previous.get("seed_hex") != args.seed_hex:
            print("[failed] --seed-hex does not match the committed seed. It reproduces "
                  "the committed run; it does not choose a new one. Omit it to sample "
                  "a fresh seed, and keep whatever that seed gives.", file=sys.stderr)
            return 1
        if previous.get("registration_sha256") != registration_sha:
            print("[failed] inputs changed since this seed was drawn: "
                  f"registration is now {registration_sha[:16]} but that seed was "
                  f"bound to {str(previous.get('registration_sha256'))[:16]}. "
                  "Sample a fresh seed instead of reusing this one.", file=sys.stderr)
            return 1

    seed_hex = args.seed_hex or secrets.token_bytes(32).hex()
    declawd.SEED = bytes.fromhex(seed_hex)
    declawd.MIN_EFFECTIVE_TOKENS = MIN_EFFECTIVE_TOKENS
    declawd.validate_parameters()
    print(f"[ok] seed sampled once       {seed_hex[:16]}...")

    segments = json.loads(template_path.read_text(encoding="utf-8"))["segments"]
    control = declawd.generate(segments, marked=False)
    marked = declawd.generate(segments, marked=True)
    control_z, control_t = z_of(control)
    marked_z, marked_t = z_of(marked)

    calibration = load_corpus("calibration")
    scored = []
    for passage in calibration:
        z, tokens = z_of(passage["text"])
        scored.append({"id": passage["id"], "author": passage["author"], "z": z, "t": tokens})
    usable = [s for s in scored if s["t"] >= MIN_EFFECTIVE_TOKENS]

    # Smallest threshold on a 0.05 grid meeting the declared false-positive
    # target on the human calibration corpus. The marked fixture plays no part:
    # choosing a threshold partly so the demonstration succeeds would be tuning
    # the detector to its own demo, and it made the procedure fail outright
    # whenever the seed produced a weaker fixture.
    threshold = None
    for step in range(0, 400):
        candidate = step * 0.05
        crossings = sum(1 for s in usable if s["z"] > candidate)
        if crossings / len(usable) <= FALSE_POSITIVE_TARGET:
            threshold = candidate
            break
    if threshold is None:
        print("[failed] no threshold meets the declared false-positive target", file=sys.stderr)
        return 1
    fixture_detected = marked_z > threshold

    crossings = sum(1 for s in usable if s["z"] > threshold)
    low, high = wilson(crossings, len(usable))
    calibration_payload = {
        "registration_sha256": registration_sha,
        "seed_hex": seed_hex,
        "threshold": round(threshold, 2),
        "min_effective_tokens": MIN_EFFECTIVE_TOKENS,
        "marked_fixture": {"z": round(marked_z, 2), "effective_tokens": marked_t,
                           "detected": fixture_detected},
        "note_on_threshold": "Chosen from the human calibration corpus alone. Whether "
                             "the marked fixture clears it is an outcome, not a constraint.",
        "control_fixture": {"z": round(control_z, 2), "effective_tokens": control_t},
        "calibration_corpus": {
            "passages": len(scored),
            "usable": len(usable),
            "authors": sorted({s["author"] for s in scored}),
            "crossings": crossings,
            "rate": round(crossings / len(usable), 4),
            "wilson_95": [round(low, 4), round(high, 4)],
            "max_z": round(max(s["z"] for s in usable), 2),
        },
    }
    write_json(CALIBRATION_REPORT, calibration_payload)
    print(f"[ok] threshold frozen        {threshold:.2f}")

    write_json(PROFILE, {
        "profile_id": "declawd-v1",
        "registration_sha256": registration_sha,
        "seed_hex": seed_hex,
        "gamma": {"numerator": declawd.GAMMA_NUM, "denominator": declawd.GAMMA_DEN},
        "threshold": {"numerator": round(threshold, 2), "denominator": 1},
        "min_effective_tokens": MIN_EFFECTIVE_TOKENS,
        "domain_separator": declawd.DOMAIN_SEPARATOR.decode("ascii"),
        "tokeniser_pattern": declawd.TOKEN_PATTERN.pattern,
        "calibration_report_sha256": digest(CALIBRATION_REPORT),
    })
    print(f"[ok] profile written         {digest(PROFILE)[:16]}")

    # The evaluation corpus is opened exactly once, after the threshold is frozen.
    evaluation = load_corpus("evaluation")
    rows = []
    for passage in evaluation:
        z, tokens = z_of(passage["text"])
        rows.append({
            "id": passage["id"], "author": passage["author"],
            "z": round(z, 3), "effective_tokens": tokens,
            "crossed": bool(z > threshold and tokens >= MIN_EFFECTIVE_TOKENS),
        })
    usable_rows = [r for r in rows if r["effective_tokens"] >= MIN_EFFECTIVE_TOKENS]
    crossed = [r for r in usable_rows if r["crossed"]]
    low, high = wilson(len(crossed), len(usable_rows))

    by_author = {}
    for row in usable_rows:
        entry = by_author.setdefault(row["author"], {"passages": 0, "crossings": 0})
        entry["passages"] += 1
        entry["crossings"] += int(row["crossed"])

    write_json(EVALUATION_REPORT, {
        "profile_sha256": digest(PROFILE),
        "threshold": round(threshold, 2),
        "scored_after_threshold_frozen": True,
        "note_on_procedure": "The evaluation corpus is scored in a single pass after "
                             "the threshold is frozen, and is never consulted while "
                             "choosing it. Re-running this script re-scores it; the "
                             "published figures are those of the committed run.",
        "passages": len(rows),
        "usable": len(usable_rows),
        "below_minimum": len(rows) - len(usable_rows),
        "authors": len(by_author),
        "crossings": len(crossed),
        "rate": round(len(crossed) / len(usable_rows), 4),
        "wilson_95": [round(low, 4), round(high, 4)],
        "by_author": by_author,
        "crossing_ids": [r["id"] for r in crossed],
        "scores": sorted(r["z"] for r in usable_rows),
        "note": "All results reported. No example was selected. A finite corpus with no "
                "crossing would not establish that the false-positive rate is zero.",
    })
    print(f"[ok] evaluation opened once  {len(crossed)}/{len(usable_rows)} crossed "
          f"({100 * len(crossed) / len(usable_rows):.2f} per cent, "
          f"95% CI {100 * low:.2f} to {100 * high:.2f})")
    print(f"[ok] marked z={marked_z:.2f}  control z={control_z:.2f}  threshold {threshold:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
