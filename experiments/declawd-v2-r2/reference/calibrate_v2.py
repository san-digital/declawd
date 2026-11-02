#!/usr/bin/env python3
"""Register, sample once and reproduce the separate declawd-v2 experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys

import candidate_review
import declawd

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "declawd-v2-r2"
DOMAIN_SEPARATOR = b"declawd/v2-r2/green"
MINIMUM = 200
GROUPS = ("prefix_199", "prefix_200", "prefix_201", "full")
CALIBRATION_GROUPS = GROUPS[1:]
INPUTS = (
    "fixtures/template-v2.json",
    "fixtures/candidate-review-v2.json",
    "fixtures/corpus.json",
    "fixtures/rewrite.json",
    "fixtures/perturbations.json",
    "reference/declawd.py",
    "reference/candidate_review.py",
    "reference/calibrate_v2.py",
    "docs/PLAN-V2.md",
    "experiments/declawd-v2-attempt-1/archive-manifest.json",
)
REGISTRATION = "fixtures/registration-v2.json"
SEED = "fixtures/seed-v2.json"
OUTPUTS = (
    "fixtures/profile-v2.json",
    "reports/calibration-report-v2.json",
    "reports/evaluation-report-v2.json",
    "vectors/scoring-v2.json",
    "vectors/controlled-removal-v2.json",
)


def encoded(document: dict) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(root: Path, name: str) -> dict:
    return json.loads((root / name).read_bytes())


def registration_payload(root: Path) -> dict:
    candidate_review.validate(root / INPUTS[0], root / INPUTS[1])
    segments = read(root, INPUTS[0])["segments"]
    control = "".join(part if isinstance(part, str) else part[0] for part in segments)
    if declawd.count_contexts(control) < 201:
        raise ValueError("control fixture must cover every registered boundary")
    corpus = read(root, "fixtures/corpus.json")["passages"]
    if len({p["id"] for p in corpus}) != len(corpus):
        raise ValueError("corpus passage identifiers must be unique")
    if any(p["split"] not in ("calibration", "evaluation") for p in corpus):
        raise ValueError("unknown corpus split")
    splits = {
        name: [p for p in corpus if p["split"] == name]
        for name in ("calibration", "evaluation")
    }
    if any(
        not passages
        or not any(declawd.count_contexts(p["text"]) >= 201 for p in passages)
        for passages in splits.values()
    ):
        raise ValueError("both corpus splits must cover every registered boundary")
    if {p["author"] for p in splits["calibration"]} & {
        p["author"] for p in splits["evaluation"]
    }:
        raise ValueError("calibration and evaluation authors overlap")
    files = {name: digest((root / name).read_bytes()) for name in INPUTS}
    return {
        "registration_id": PROFILE_ID,
        "previous_attempt": {
            "profile_id": "declawd-v2",
            "source_commit": "77c1d6e9dfad7018491308e13ddd5a4a1b9d08e0",
            "archive": "experiments/declawd-v2-attempt-1",
            "reason": "candidate review missed a empty and a additional article agreement",
        },
        "targets": {
            "min_effective_tokens": MINIMUM,
            "false_positive_rate_at_or_below": 0.02,
        },
        "domain_separator": DOMAIN_SEPARATOR.decode("ascii"),
        "gamma": {"numerator": 1, "denominator": 4},
        "tokeniser": {
            "pattern": declawd.TOKEN_PATTERN.pattern,
            "folding": "ASCII A-Z to a-z",
        },
        "canonicaliser": {"zero_width": "U+200B", "confusables": declawd.CONFUSABLES},
        "template_sha256": files[INPUTS[0]],
        "corpus_sha256": files["fixtures/corpus.json"],
        "rewrite_sha256": files["fixtures/rewrite.json"],
        "perturbations_sha256": files["fixtures/perturbations.json"],
        "perturbations": read(root, "fixtures/perturbations.json")["targets"],
        "source_files": files,
        "threshold_policy": {
            "step_numerator": 5,
            "step_denominator": 100,
            "max_step": 399,
            "groups": list(CALIBRATION_GROUPS),
            "selection": "smallest threshold meeting target separately in each eligible calibration group",
            "comparison": "strict integer verdict comparison",
            "marked_fixture": "reported outcome",
        },
        "analysis": {
            "length_groups": list(GROUPS),
            "prefix_rule": "shortest original-text prefix ending at a token reaching the named distinct-pair count",
            "unit": "one verdict per source passage within each length group",
            "corpus_split": "by author, preserving the published v1 split",
            "corpus_reuse": "historical corpus previously examined for v1, including its evaluation results",
            "interval": "Wilson 95 per cent, descriptive because passages share authors and prefixes share passages",
            "selection": "all eligible passages reported, unavailable lengths counted as exclusions",
        },
        "controlled_removal": {
            "max_steps": 6,
            "selection": "lowest resulting z among reviewed alternatives in unused slots",
            "ties": "slot index then authored candidate order",
            "stop": "no strict score reduction",
        },
        "seed_policy": "commit registration before one recorded draw, retain its outcomes, refuse a second draw",
    }


def committed(root: Path, names: tuple[str, ...]) -> str:
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    for name in names:
        original = subprocess.check_output(
            ["git", "show", f"{revision}:{name}"], cwd=root
        )
        if original != (root / name).read_bytes():
            raise ValueError(f"commit the registered bytes before sampling: {name}")
        staged = subprocess.check_output(
            ["git", "diff", "--cached", "--", name], cwd=root
        )
        if staged:
            raise ValueError(f"registered file has staged changes: {name}")
    return revision


def exclusive(root: Path, name: str, data: dict) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded(data))
        stream.flush()
        os.fsync(stream.fileno())


def register(root: Path = ROOT) -> dict:
    if any((root / name).exists() for name in (SEED, *OUTPUTS)):
        raise ValueError("this registration already has a seed or outputs")
    payload = registration_payload(root)
    committed(root, INPUTS)
    exclusive(root, REGISTRATION, payload)
    return payload


def verify_registration(root: Path) -> dict:
    payload = registration_payload(root)
    if (root / REGISTRATION).read_bytes() != encoded(payload):
        raise ValueError("registered inputs or procedure changed")
    return payload


def sample(root: Path = ROOT) -> dict:
    if any((root / name).exists() for name in (SEED, *OUTPUTS)):
        raise ValueError("a seed or output already exists, reproduce the recorded run")
    verify_registration(root)
    revision = committed(root, (*INPUTS, REGISTRATION))
    with (root / SEED).open("xb") as stream:
        payload = {
            "registration_sha256": digest((root / REGISTRATION).read_bytes()),
            "registration_commit": revision,
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "seed_hex": secrets.token_bytes(32).hex(),
            "procedure": "one draw recorded before scoring, no independent witness",
        }
        stream.write(encoded(payload))
        stream.flush()
        os.fsync(stream.fileno())
    reproduce(root, write=True)
    return payload


def prefix_at_pairs(text: str, count: int) -> str | None:
    seen = set()
    previous = ""
    for match in declawd.TOKEN_PATTERN.finditer(text):
        current = declawd.fold(match.group())
        seen.add((previous, current))
        previous = current
        if len(seen) == count:
            return text[: match.end()]
    return None


def exceeds(effective: int, green: int, numerator: int) -> bool:
    n = 4 * green - effective
    return (
        effective >= MINIMUM
        and n > 0
        and 10000 * n * n > numerator * numerator * effective * 3
    )


def cohort_rows(passages: list[dict]) -> dict[str, list[dict]]:
    groups = {name: [] for name in GROUPS}
    for passage in passages:
        for name in GROUPS:
            text = (
                passage["text"]
                if name == "full"
                else prefix_at_pairs(passage["text"], int(name[7:]))
            )
            if text is None:
                continue
            result = declawd.score(text)
            groups[name].append(
                {
                    "id": passage["id"],
                    "author": passage["author"],
                    "text_sha256": digest(text.encode("utf-8")),
                    "effective_tokens": result.effective_tokens,
                    "green": result.green,
                    "z": result.z_display,
                }
            )
    return groups


def choose_threshold(groups: dict[str, list[dict]]) -> int:
    eligible = {
        name: [r for r in groups[name] if r["effective_tokens"] >= MINIMUM]
        for name in CALIBRATION_GROUPS
    }
    if any(not rows for rows in eligible.values()):
        raise ValueError("every calibration length group needs eligible passages")
    for step in range(400):
        numerator = step * 5
        if all(
            sum(exceeds(r["effective_tokens"], r["green"], numerator) for r in rows)
            * 50
            <= len(rows)
            for rows in eligible.values()
        ):
            return numerator
    raise ValueError(
        "no threshold on the registered grid meets every calibration target"
    )


def wilson(crossings: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.96
    p = crossings / total
    d = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / d
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return [round(max(0, centre - margin), 4), round(min(1, centre + margin), 4)]


def summarise(rows: list[dict], total: int, threshold: int) -> dict:
    eligible = [r for r in rows if r["effective_tokens"] >= MINIMUM]
    crossings = [
        r for r in eligible if exceeds(r["effective_tokens"], r["green"], threshold)
    ]
    by_author = {}
    for row in eligible:
        entry = by_author.setdefault(row["author"], {"passages": 0, "crossings": 0})
        entry["passages"] += 1
        entry["crossings"] += int(
            exceeds(row["effective_tokens"], row["green"], threshold)
        )
    public_rows = []
    for row in rows:
        usable = row["effective_tokens"] >= MINIMUM
        public_rows.append(
            {
                **row,
                "green": row["green"] if usable else None,
                "z": round(row["z"], 6) if usable else None,
                "crossed": exceeds(row["effective_tokens"], row["green"], threshold)
                if usable
                else None,
                "verdict": (
                    "above threshold"
                    if exceeds(row["effective_tokens"], row["green"], threshold)
                    else "below threshold"
                )
                if usable
                else "insufficient text",
            }
        )
    return {
        "passages": len(rows),
        "source_passages": total,
        "unavailable": total - len(rows),
        "usable": len(eligible),
        "below_minimum": len(rows) - len(eligible),
        "authors": len({r["author"] for r in eligible}),
        "by_author": by_author,
        "crossings": len(crossings),
        "crossing_ids": [r["id"] for r in crossings],
        "rate": round(len(crossings) / len(eligible), 4) if eligible else None,
        "wilson_95": wilson(len(crossings), len(eligible)),
        "scores": sorted(round(r["z"], 3) for r in eligible),
        "rows": public_rows,
    }


def score_record(text: str) -> dict:
    result = declawd.score(text)
    usable = result.effective_tokens >= MINIMUM
    return {
        "raw": result.raw_tokens,
        "effective": result.effective_tokens,
        "green": result.green if usable else None,
        "z": result.z_display if usable else None,
        "verdict": result.verdict,
    }


def removal_vector(segments: list, marked: str, fixture_id: str) -> dict:
    slots = []
    offset = 0
    for index, segment in enumerate(segments):
        if isinstance(segment, str):
            offset += len(segment)
        else:
            match = declawd.TOKEN_PATTERN.match(marked, offset)
            if match is None or match.group() not in segment:
                raise ValueError(f"marked text no longer matches slot {index}")
            slots.append((index, offset, match.group(), segment))
            offset = match.end()
    substitutions = []
    steps = []
    used = set()

    def apply(changes: list[dict]) -> str:
        text = marked
        for change in sorted(changes, key=lambda c: c["scalar_offset"], reverse=True):
            start = change["scalar_offset"]
            text = (
                text[:start] + change["after"] + text[start + len(change["before"]) :]
            )
        return text

    text = marked
    for _ in range(6):
        best = None
        current_z = declawd.score(text).z_display
        for index, start, before, candidates in slots:
            if index in used:
                continue
            for order, after in enumerate(candidates):
                if after == before:
                    continue
                change = {"scalar_offset": start, "before": before, "after": after}
                candidate_text = apply([*substitutions, change])
                result = declawd.score(candidate_text)
                if (
                    result.effective_tokens < MINIMUM
                    or result.z_display is None
                    or result.z_display >= current_z
                ):
                    continue
                key = (result.z_display, index, order)
                if best is None or key < best[0]:
                    best = (key, change, candidate_text)
        if best is None:
            break
        used.add(best[0][1])
        substitutions.append(best[1])
        text = best[2]
        steps.append(
            {
                "applied": len(substitutions),
                "substitution": best[1],
                "score": score_record(text),
            }
        )
    count = declawd.score(marked).effective_tokens
    return {
        "schema": "declawd.controlled-removal/v1",
        "profile_id": PROFILE_ID,
        "fixture_id": fixture_id,
        "position_model": "zero-based Unicode scalar offsets in the original marked passage",
        "source_text": marked,
        "source_score": score_record(marked),
        "substitutions": substitutions,
        "steps": steps,
        "expected_text": text,
        "expected_score": score_record(text),
        "one_green_context_z_step": 4 / math.sqrt(3 * count),
        "note": "Up to six reductions chosen by the registered rule using the public seed and reviewed candidates. Original offsets are applied from right to left.",
    }


def reproduce(root: Path = ROOT, write: bool = False) -> dict[str, dict]:
    registration = verify_registration(root)
    seed = read(root, SEED)
    registration_sha = digest((root / REGISTRATION).read_bytes())
    if (
        seed["registration_sha256"] != registration_sha
        or len(bytes.fromhex(seed["seed_hex"])) != 32
    ):
        raise ValueError("seed is not bound to this registration")
    if (root / OUTPUTS[1]).exists():
        existing = read(root, OUTPUTS[1])
        expected = (
            registration_sha,
            seed["seed_hex"],
            digest((root / SEED).read_bytes()),
        )
        actual = tuple(
            existing.get(key)
            for key in ("registration_sha256", "seed_hex", "seed_record_sha256")
        )
        if actual != expected:
            raise ValueError(
                "recorded seed differs from the existing calibration report"
            )
    declawd.DOMAIN_SEPARATOR = DOMAIN_SEPARATOR
    declawd.SEED = bytes.fromhex(seed["seed_hex"])
    declawd.GAMMA_NUM, declawd.GAMMA_DEN = 1, 4
    declawd.MIN_EFFECTIVE_TOKENS = MINIMUM
    declawd.THRESHOLD_NUM, declawd.THRESHOLD_DEN = 0, 100
    declawd.validate_parameters()
    corpus = read(root, "fixtures/corpus.json")["passages"]
    calibration = [p for p in corpus if p["split"] == "calibration"]
    evaluation = [p for p in corpus if p["split"] == "evaluation"]
    if {p["author"] for p in calibration} & {p["author"] for p in evaluation}:
        raise ValueError("calibration and evaluation authors overlap")
    calibration_groups = cohort_rows(calibration)
    threshold = choose_threshold(calibration_groups)
    declawd.THRESHOLD_NUM = threshold
    template = read(root, "fixtures/template-v2.json")
    segments = template["segments"]
    marked = declawd.generate(segments, marked=True)
    control = declawd.generate(segments, marked=False)
    group_reports = {
        name: summarise(rows, len(calibration), threshold)
        for name, rows in calibration_groups.items()
    }
    marked_score, control_score = score_record(marked), score_record(control)
    calibration_report = {
        "registration_sha256": registration_sha,
        "seed_hex": seed["seed_hex"],
        "seed_record_sha256": digest((root / SEED).read_bytes()),
        "threshold": threshold / 100,
        "min_effective_tokens": MINIMUM,
        "marked_fixture": {
            "z": round(marked_score["z"], 2),
            "effective_tokens": marked_score["effective"],
            "detected": marked_score["verdict"] == "above threshold",
        },
        "control_fixture": {
            "z": round(control_score["z"], 2),
            "effective_tokens": control_score["effective"],
        },
        "calibration_corpus": group_reports["full"],
        "length_groups": group_reports,
        "note_on_threshold": registration["threshold_policy"]["selection"],
    }
    profile = {
        "profile_id": PROFILE_ID,
        "registration_sha256": registration_sha,
        "seed_hex": seed["seed_hex"],
        "domain_separator": DOMAIN_SEPARATOR.decode("ascii"),
        "gamma": registration["gamma"],
        "threshold": {"numerator": threshold / 100, "denominator": 1},
        "min_effective_tokens": MINIMUM,
        "tokeniser_pattern": declawd.TOKEN_PATTERN.pattern,
        "calibration_report_sha256": digest(encoded(calibration_report)),
    }
    evaluation_groups = {
        name: summarise(rows, len(evaluation), threshold)
        for name, rows in cohort_rows(evaluation).items()
    }
    evaluation_report = {
        **evaluation_groups["full"],
        "profile_sha256": digest(encoded(profile)),
        "threshold": threshold / 100,
        "scored_after_threshold_frozen": True,
        "length_groups": evaluation_groups,
        "note_on_procedure": "Threshold selected on calibration authors before scoring evaluation authors. The historical corpus was previously published and examined for v1.",
        "note": "All eligible results reported. Length groups share passages and passages share authors. Wilson intervals describe this corpus and are not population guarantees.",
    }
    examples = [
        "",
        "a",
        "The quick brown fox jumps over the lazy dog.",
        "spam spam spam spam spam",
        "can't can’t naive naïve co-operate",
        "ab\u200bcd",
        "a😀b",
        "one\r\ntwo\tthree",
        marked,
        control,
    ]
    examples += [prefix_at_pairs(control, n) for n in (199, 200, 201)]
    if any(text is None for text in examples):
        raise ValueError("control fixture must cover every registered boundary")
    scoring = {
        "profile": profile,
        "vectors": [{"text": text, **score_record(text)} for text in examples],
    }
    documents = dict(
        zip(
            OUTPUTS,
            (
                profile,
                calibration_report,
                evaluation_report,
                scoring,
                removal_vector(segments, marked, template["fixture_id"]),
            ),
        )
    )
    for name, document in documents.items():
        data = encoded(document)
        if write:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(data)
        elif (root / name).read_bytes() != data:
            raise ValueError(f"reproduction differs: {name}")
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "sample", "reproduce"))
    parser.add_argument(
        "--write",
        action="store_true",
        help="restore deterministic outputs from the existing seed",
    )
    args = parser.parse_args()
    try:
        if args.write and args.command != "reproduce":
            raise ValueError("--write applies only to reproduction")
        if args.command == "register":
            register()
        elif args.command == "sample":
            sample()
        else:
            reproduce(write=args.write)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"[failed] {error}", file=sys.stderr)
        return 1
    print(f"[ok] {PROFILE_ID} {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
