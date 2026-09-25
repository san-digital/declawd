"""Check that an agent review covers each candidate and its exact sentence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
SCHEMA = "declawd.candidate-review/v2"
METHOD = "agent review of grammar and unchanged operational meaning"


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _segments(template: dict) -> list:
    segments = template.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("template segments must be a non-empty list")
    slots = 0
    for index, segment in enumerate(segments):
        if isinstance(segment, str):
            continue
        if not isinstance(segment, list) or len(segment) < 2:
            raise ValueError(f"segment {index} must be literal text or at least two candidates")
        if any(not isinstance(word, str) or TOKEN.fullmatch(word) is None for word in segment):
            raise ValueError(f"segment {index} contains a candidate that is not one ASCII token")
        if len({word.lower() for word in segment}) != len(segment):
            raise ValueError(f"segment {index} has duplicate candidates after ASCII folding")
        slots += 1
    if not slots:
        raise ValueError("template must contain candidate slots")
    return segments


def render_variants(template_path: Path) -> list[dict]:
    """Render each candidate's complete sentence with the other slots at their defaults."""
    segments = _segments(_load(Path(template_path)))
    variants = []
    for index, segment in enumerate(segments):
        if isinstance(segment, str):
            continue
        for candidate in segment:
            parts = [part if isinstance(part, str) else part[0] for part in segments]
            parts[index] = candidate
            text = "".join(parts)
            start = sum(len(part) for part in parts[:index])
            end = start + len(candidate)
            if (start and (text[start - 1].isalpha() or text[start - 1] == "'")) or (
                end < len(text) and (text[end].isalpha() or text[end] == "'")
            ):
                raise ValueError(f"segment {index} joins a candidate to an adjacent token")
            boundaries = list(SENTENCE_END.finditer(text))
            left = max((match.end() for match in boundaries if match.end() <= start), default=0)
            right = next((match.end() for match in boundaries if match.start() >= end), None)
            if right is None:
                raise ValueError(f"segment {index} has no complete sentence ending")
            variants.append({
                "segment_index": index,
                "candidate": candidate,
                "sentence": text[left:right].strip(),
            })
    return variants


def validate(template_path: Path, review_path: Path) -> None:
    """Require complete, current review records without claiming to assess grammar in code."""
    template_path = Path(template_path)
    review = _load(Path(review_path))
    expected = render_variants(template_path)
    if review.get("schema") != SCHEMA or review.get("method") != METHOD:
        raise ValueError("review schema or review method is missing or unsupported")
    if review.get("template_sha256") != hashlib.sha256(template_path.read_bytes()).hexdigest():
        raise ValueError("candidate review is stale: template SHA-256 differs")
    entries = review.get("entries")
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("candidate review must cover every candidate exactly once")
    by_key = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each candidate review must be an object")
        index, candidate = entry.get("segment_index"), entry.get("candidate")
        if type(index) is not int or not isinstance(candidate, str):
            raise ValueError("each candidate review needs an integer segment and a candidate")
        key = (index, candidate)
        if key in by_key:
            raise ValueError(f"duplicate candidate review: {key}")
        if entry.get("grammar_approved") is not True or entry.get("same_job_approved") is not True:
            raise ValueError(f"candidate lacks both review approvals: {key}")
        if not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
            raise ValueError(f"candidate lacks a review rationale: {key}")
        by_key[key] = entry
    for variant in expected:
        key = (variant["segment_index"], variant["candidate"])
        if key not in by_key or by_key[key].get("sentence") != variant["sentence"]:
            raise ValueError(f"candidate review is missing or its sentence differs: {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("review", type=Path)
    args = parser.parse_args()
    try:
        validate(args.template, args.review)
    except ValueError as error:
        parser.exit(1, f"[failed] {error}\n")
    print(f"[ok] candidate review covers {len(render_variants(args.template))} rendered variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
