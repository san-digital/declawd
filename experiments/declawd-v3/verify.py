#!/usr/bin/env python3
"""Verify recorded input, registration, seed and output order from Git history."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reference"))
import calibrate_v3 as protocol


def verify_history(root: Path = ROOT) -> dict:
    root = root.resolve()
    top = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()).resolve()
    prefix = root.relative_to(top)

    def git(*arguments: str) -> bytes:
        return subprocess.check_output(["git", *arguments], cwd=top, stderr=subprocess.PIPE)

    def recorded(commit: str, name: str) -> bytes:
        return git("show", f"{commit}:{(prefix / name).as_posix()}")

    def first_add(name: str) -> str:
        commits = git("log", "--reverse", "--format=%H", "--diff-filter=A", "--", (prefix / name).as_posix()).decode().splitlines()
        if not commits:
            raise ValueError(f"no committed history for {name}")
        return commits[0]

    seed = json.loads((root / protocol.SEED).read_bytes())
    registration_commit = seed["registration_commit"]
    for name in (*protocol.INPUTS, protocol.REGISTRATION):
        if recorded(registration_commit, name) != (root / name).read_bytes():
            raise ValueError(f"registered bytes differ from registration commit: {name}")
    seed_commit = first_add(protocol.SEED)
    if recorded(seed_commit, protocol.SEED) != (root / protocol.SEED).read_bytes():
        raise ValueError("seed changed after its first committed draw")
    if registration_commit == seed_commit:
        raise ValueError("registration and seed need separate commits")
    git("merge-base", "--is-ancestor", registration_commit, seed_commit)
    for name in protocol.OUTPUTS:
        try:
            recorded(seed_commit, name)
        except subprocess.CalledProcessError:
            continue
        raise ValueError(f"output already existed when seed was committed: {name}")
    output_commits = {}
    for name in protocol.OUTPUTS:
        commit = first_add(name)
        if commit == seed_commit:
            raise ValueError("outputs need a commit after the seed")
        git("merge-base", "--is-ancestor", seed_commit, commit)
        if recorded(commit, name) != (root / name).read_bytes():
            raise ValueError(f"output changed after its first recorded run: {name}")
        output_commits[name] = commit
    protocol.reproduce(root)
    return {"registration_commit": registration_commit, "seed_commit": seed_commit, "output_commits": output_commits}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = verify_history()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"[failed] {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
