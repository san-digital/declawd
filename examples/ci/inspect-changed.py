#!/usr/bin/env python3
"""Combine changed text reports into one SARIF run without losing locations."""
import argparse
import json
import os
from pathlib import Path
import subprocess


SUFFIXES = (b".md", b".markdown", b".txt")


def inspect_changed(base_ref, output):
    changed = subprocess.check_output([
        "git", "diff", "--name-only", "--diff-filter=d", "-z", f"{base_ref}...HEAD", "--"
    ])
    paths = [os.fsdecode(path) for path in changed.split(b"\0") if path.endswith(SUFFIXES)]
    if not paths:
        output.unlink(missing_ok=True)
        return 0

    combined = None
    rules = {}
    notifications = {}
    for path in paths:
        report = json.loads(subprocess.check_output([
            "declawd", "inspect", "--sarif", "--exit-zero", "--", f"./{path}"
        ]))
        run = report["runs"][0]
        if not run["artifacts"][0]["mimeType"].startswith("text/"):
            raise ValueError(f"changed text path contains non-text data: {path!r}")
        if combined is None:
            combined = report
            combined["runs"][0] = {
                **run, "artifacts": [], "results": [],
                "automationDetails": {"id": "declawd/changed-text/"},
            }
        target = combined["runs"][0]
        offset = len(target["artifacts"])
        for result in run["results"]:
            for location in result.get("locations", []):
                location["physicalLocation"]["artifactLocation"]["index"] += offset
        target["artifacts"].extend(run["artifacts"])
        target["results"].extend(run["results"])
        for rule in run["tool"]["driver"]["rules"]:
            rules[rule["id"]] = rule
        for note in run["invocations"][0]["toolExecutionNotifications"]:
            notifications[json.dumps(note, sort_keys=True)] = note
        if len(target["results"]) > 25_000:
            raise ValueError("GitHub accepts at most 25,000 results per run; narrow this scan")
    combined["runs"][0]["tool"]["driver"]["rules"] = list(rules.values())
    combined["runs"][0]["invocations"][0]["toolExecutionNotifications"] = list(notifications.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
    return len(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = inspect_changed(args.base_ref, args.output)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"files={count}\n")
    print(f"Inspected {count} changed text files. No provider verifier ran.")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(
                f"Inspected {count} changed text files for registered carriers. "
                "No provider verifier ran. Confusable letters and statistical token-choice "
                "watermarks were not inspected. Passing this job does not establish how "
                "the text was written. SARIF viewers may omit review and untested-channel "
                "results; download the retained SARIF for the complete report.\n"
            )


if __name__ == "__main__":
    main()
