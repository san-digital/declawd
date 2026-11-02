#!/usr/bin/env python3
"""Verify frozen v3 bytes and commit order against its pinned evidence tag."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TAG = "declawd-v3-evidence-2026-11-02"
EVIDENCE_COMMIT = "06fac8a1057ff43d564e2f144bf8949b7451f65c"
PREFIX = Path("experiments/declawd-v3")
INPUTS = (
    "fixtures/template-v3.json", "fixtures/candidate-review-v3.json", "fixtures/corpus.json",
    "fixtures/rewrite.json", "fixtures/perturbations.json", "reference/declawd.py",
    "reference/candidate_review.py", "reference/calibrate_v3.py", "docs/PLAN-V3.md",
    "archive-manifest-r2.json", "reference/test_protocol.py", "verify.py",
)
REGISTRATION = "fixtures/registration-v3.json"
SEED = "fixtures/seed-v3.json"
OUTPUTS = (
    "fixtures/profile-v3.json", "reports/calibration-report-v3.json", "reports/evaluation-report-v3.json",
    "vectors/scoring-v3.json", "vectors/controlled-removal-v3.json",
)


def verify_history(root: Path = ROOT, *, fetch_history: bool = False) -> dict:
    top = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()).resolve()
    experiment = top / PREFIX

    def git(*arguments: str) -> bytes:
        return subprocess.check_output(["git", *arguments], cwd=top, stderr=subprocess.PIPE)

    try:
        git("show-ref", "--verify", "--quiet", f"refs/tags/{TAG}")
    except subprocess.CalledProcessError:
        if not fetch_history:
            raise ValueError(f"missing evidence tag {TAG}, use --fetch-history explicitly") from None
        git("fetch", "--no-tags", "origin", f"refs/tags/{TAG}:refs/tags/{TAG}")
    try:
        evidence_commit = git("rev-parse", f"refs/tags/{TAG}^{{commit}}").decode().strip()
    except subprocess.CalledProcessError:
        raise ValueError(f"unreadable evidence tag {TAG}") from None
    if evidence_commit != EVIDENCE_COMMIT:
        raise ValueError(f"evidence tag moved: expected {EVIDENCE_COMMIT}, got {evidence_commit}")

    def recorded(commit: str, name: str) -> bytes:
        return git("show", f"{commit}:{(PREFIX / name).as_posix()}")

    def first_add(name: str) -> str:
        commits = git("log", "--reverse", "--format=%H", "--diff-filter=A", EVIDENCE_COMMIT,
                      "--", (PREFIX / name).as_posix()).decode().splitlines()
        if not commits:
            raise ValueError(f"no tagged history for {name}")
        return commits[0]

    for name in (*INPUTS, REGISTRATION, SEED, *OUTPUTS):
        if recorded(EVIDENCE_COMMIT, name) != (experiment / name).read_bytes():
            raise ValueError(f"current bytes differ from tagged evidence: {name}")
    seed = json.loads((experiment / SEED).read_bytes())
    registration_commit = seed["registration_commit"]
    for name in (*INPUTS, REGISTRATION):
        if recorded(registration_commit, name) != (experiment / name).read_bytes():
            raise ValueError(f"registered bytes differ from registration commit: {name}")
    seed_commit = first_add(SEED)
    if recorded(seed_commit, SEED) != (experiment / SEED).read_bytes():
        raise ValueError("seed changed after its first committed draw")
    if registration_commit == seed_commit:
        raise ValueError("registration and seed need separate commits")
    git("merge-base", "--is-ancestor", registration_commit, seed_commit)
    for name in OUTPUTS:
        try:
            recorded(seed_commit, name)
        except subprocess.CalledProcessError:
            continue
        raise ValueError(f"output already existed when seed was committed: {name}")
    output_commits = {}
    for name in OUTPUTS:
        commit = first_add(name)
        if commit == seed_commit:
            raise ValueError("outputs need a commit after the seed")
        git("merge-base", "--is-ancestor", seed_commit, commit)
        if recorded(commit, name) != (experiment / name).read_bytes():
            raise ValueError(f"output changed after its first recorded run: {name}")
        output_commits[name] = commit
    subprocess.run([sys.executable, str(experiment / "reference/calibrate_v3.py"), "reproduce"],
                   cwd=top, check=True, capture_output=True)
    return {"evidence_tag": TAG, "evidence_commit": evidence_commit, "registration_commit": registration_commit,
            "seed_commit": seed_commit, "output_commits": output_commits}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-history", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_history(fetch_history=args.fetch_history)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"[failed] {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
