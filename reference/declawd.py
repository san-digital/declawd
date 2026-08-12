#!/usr/bin/env python3
"""Public KGW-inspired text watermark used by declawd.com.

This educational implementation has a published seed. It does not detect,
reproduce, remove or interoperate with any production watermark, and its scores
must not be used to support authorship, employment, disciplinary, academic or
forensic decisions.

The reference implementation for declawd.com. The browser implementation is
tested against the vectors this module produces, so every rule here that could
differ between Python and JavaScript is specified rather than left to the
runtime: the scanner treats non-matching scalars as delimiters instead of
deleting them, the green predicate hashes length-prefixed UTF-8 bytes, and the
verdict is decided in integers so no square root is ever compared.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Iterator, NamedTuple, Optional

# The scanner pattern is normative and shared with the browser implementation.
# It runs over the original scalar sequence; characters it does not match are
# delimiters, never deleted. Deleting them first would make a zero-width
# insertion invisible to tokenisation, which is the whole perturbation demo.
TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

DOMAIN_SEPARATOR = b"declawd/v1/green"

# Deliberately invalid until a profile is loaded. Shipping a usable default here
# meant scoring the committed fixture directly returned a different verdict from
# the published one, which is worse than refusing to score at all.
SEED = b""

GAMMA_NUM = 1
GAMMA_DEN = 4
THRESHOLD_NUM = 4
THRESHOLD_DEN = 1

# Calibrated at the registration step; the placeholder is deliberately
# invalid so an uncalibrated profile cannot be shipped by accident.
MIN_EFFECTIVE_TOKENS = 0

ZERO_WIDTH_SPACE = "​"

# One-to-one confusable mappings the demo itself introduces, and the only ones
# the canonicaliser reverses. This is not a general Unicode folding table: on
# arbitrary text these mappings would corrupt legitimate Cyrillic.
CONFUSABLES = {
    "а": "a",  # Cyrillic small letter a
    "е": "e",  # Cyrillic small letter ie
    "о": "o",  # Cyrillic small letter o
    "р": "p",  # Cyrillic small letter er
    "с": "c",  # Cyrillic small letter es
}

VALID_TRANSITIONS = {
    ("pristine", "perturb"): "perturbed",
    ("perturbed", "canonicalise"): "analysed",
    ("pristine", "rewrite"): "rewritten",
    ("rewritten", "canonicalise"): "rewritten-analysed",
}

VERDICT_DETECTED = "above threshold"
VERDICT_NOT_DETECTED = "below threshold"
VERDICT_INSUFFICIENT = "insufficient text"


class DeclawdError(RuntimeError):
    pass


class Score(NamedTuple):
    raw_tokens: int
    effective_tokens: int
    green: int
    verdict: str

    @property
    def z_display(self) -> Optional[float]:
        """Human-readable z, or None when undefined. Never NaN or infinity."""
        if self.effective_tokens == 0:
            return None
        numerator = GAMMA_DEN * self.green - GAMMA_NUM * self.effective_tokens
        denominator = self.effective_tokens * GAMMA_NUM * (GAMMA_DEN - GAMMA_NUM)
        if denominator <= 0:
            return None
        return numerator / math.sqrt(denominator)


def load_profile(path) -> None:
    """Adopt a frozen profile. Scoring is refused until this has been called."""
    import json
    from pathlib import Path as _Path
    global SEED, MIN_EFFECTIVE_TOKENS, THRESHOLD_NUM, THRESHOLD_DEN, GAMMA_NUM, GAMMA_DEN
    profile = json.loads(_Path(path).read_text(encoding="utf-8"))
    GAMMA_NUM = int(profile["gamma"]["numerator"])
    GAMMA_DEN = int(profile["gamma"]["denominator"])
    SEED = bytes.fromhex(profile["seed_hex"])
    MIN_EFFECTIVE_TOKENS = int(profile["min_effective_tokens"])
    THRESHOLD_NUM = int(round(float(profile["threshold"]["numerator"]) * 100))
    THRESHOLD_DEN = 100
    validate_parameters()


def validate_parameters() -> None:
    """Reject a profile whose parameters are outside their permitted domains."""
    if not 0 < GAMMA_NUM < GAMMA_DEN:
        raise DeclawdError(f"gamma out of range: {GAMMA_NUM}/{GAMMA_DEN}")
    if math.gcd(GAMMA_NUM, GAMMA_DEN) != 1:
        raise DeclawdError(f"gamma not in lowest terms: {GAMMA_NUM}/{GAMMA_DEN}")
    if THRESHOLD_NUM < 0:
        raise DeclawdError(f"negative threshold numerator: {THRESHOLD_NUM!r}")
    if THRESHOLD_DEN <= 0:
        raise DeclawdError(f"non-positive threshold denominator: {THRESHOLD_DEN!r}")
    if MIN_EFFECTIVE_TOKENS <= 0:
        raise DeclawdError(f"minimum effective tokens must be positive: {MIN_EFFECTIVE_TOKENS!r}")
    if len(SEED) != 32:
        raise DeclawdError(
            "no profile loaded: call load_profile() with declawd/fixtures/profile-v1.json"
            if not SEED else f"seed must be exactly 32 bytes, got {len(SEED)}")


def scan(text: str) -> list[str]:
    """Return the scored ASCII token runs, leaving the passage itself unchanged.

    Non-matching scalars delimit tokens. They are never removed before matching,
    which is why an inserted zero-width character splits a token in two.
    """
    return TOKEN_PATTERN.findall(text)


def fold(token: str) -> str:
    """ASCII-only case mapping. Non-ASCII scalars cannot appear in a scored token."""
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in token)


def reject_lone_surrogates(text: str) -> None:
    for index, character in enumerate(text):
        if 0xD800 <= ord(character) <= 0xDFFF:
            raise DeclawdError(f"unpaired surrogate at scalar index {index}")


def is_green(previous_token: str, token: str) -> bool:
    """The keyed green predicate, over length-prefixed UTF-8 bytes.

    Length prefixes remove concatenation ambiguity without banning any byte, so
    no separator character has to be excluded from the alphabet.
    """
    if len(SEED) != 32:
        raise DeclawdError(
            "no profile loaded: call load_profile() with declawd/fixtures/profile-v1.json")
    previous_bytes = previous_token.encode("utf-8")
    token_bytes = token.encode("utf-8")
    digest = hashlib.sha256(
        DOMAIN_SEPARATOR
        + SEED
        + len(previous_bytes).to_bytes(4, "big")
        + previous_bytes
        + len(token_bytes).to_bytes(4, "big")
        + token_bytes
    ).digest()
    value = int.from_bytes(digest[:8], "big")
    return value * GAMMA_DEN < GAMMA_NUM * (1 << 64)


def contexts(tokens: list[str]) -> Iterator[tuple[str, str]]:
    """Yield (previous, current) pairs, the first against an empty sentinel."""
    previous = ""
    for token in tokens:
        current = fold(token)
        yield previous, current
        previous = current


def count_contexts(text: str) -> int:
    """Distinct scored contexts, independent of any seed.

    Corpus construction needs this before a profile exists, so it must not
    reach the green predicate.
    """
    reject_lone_surrogates(text)
    return len({c for c in contexts(scan(text))})


def score(text: str) -> Score:
    """Score a passage, masking repeated contexts.

    A context is counted on first occurrence only. Later occurrences are neither
    green nor red and do not increment the effective token count, following the
    KGW paper's remedy for repetition-driven false positives. Without this, a
    repetitive human passage accumulates an artificially high score.
    """
    reject_lone_surrogates(text)
    tokens = scan(text)
    seen: set[tuple[str, str]] = set()
    effective = 0
    green = 0
    for context in contexts(tokens):
        if context in seen:
            continue
        seen.add(context)
        effective += 1
        if is_green(*context):
            green += 1
    return Score(
        raw_tokens=len(tokens),
        effective_tokens=effective,
        green=green,
        verdict=verdict(effective, green),
    )


def verdict(effective_tokens: int, green: int) -> str:
    """Decide the verdict in integers, so no float comparison can differ across runtimes.

    For gamma = a/b and threshold = p/q, z >= p/q reduces to q^2*n^2 >= p^2*d
    with n = b*G - a*T and d = T*a*(b-a). The comparison here is strict.
    """
    if effective_tokens < MIN_EFFECTIVE_TOKENS:
        return VERDICT_INSUFFICIENT
    n = GAMMA_DEN * green - GAMMA_NUM * effective_tokens
    if n <= 0:
        return VERDICT_NOT_DETECTED
    d = effective_tokens * GAMMA_NUM * (GAMMA_DEN - GAMMA_NUM)
    if THRESHOLD_DEN * THRESHOLD_DEN * n * n > THRESHOLD_NUM * THRESHOLD_NUM * d:
        return VERDICT_DETECTED
    return VERDICT_NOT_DETECTED


def check_candidates(candidates: list[str]) -> None:
    """Enforce the generation rules that keep two implementations in step."""
    if not candidates:
        raise DeclawdError("empty candidate list")
    folded = [fold(c) for c in candidates]
    for candidate, lowered in zip(candidates, folded):
        if TOKEN_PATTERN.fullmatch(lowered) is None:
            raise DeclawdError(f"candidate is not a single ASCII token: {candidate!r}")
    if len(set(folded)) != len(folded):
        raise DeclawdError(f"candidates not distinct after folding: {candidates!r}")


def select(previous_token: str, candidates: list[str]) -> str:
    """Pick the first green candidate in authored order, else the default.

    The authored order is normative. Without it, two implementations could both
    be correct and still emit different passages whenever more than one
    candidate is green.
    """
    check_candidates(candidates)
    for candidate in candidates:
        if is_green(previous_token, fold(candidate)):
            return candidate
    return candidates[0]


def generate(segments: list, marked: bool) -> str:
    """Build a passage from literal strings and candidate slots.

    The control takes every default; the marked version prefers a green
    candidate where one exists. Both read as ordinary prose, which is the point:
    the difference is a statistical preference, not a visible artefact.
    """
    parts: list[str] = []
    previous = ""
    for segment in segments:
        if isinstance(segment, str):
            parts.append(segment)
            tokens = scan(segment)
            if tokens:
                previous = fold(tokens[-1])
            continue
        chosen = select(previous, segment) if marked else segment[0]
        parts.append(chosen)
        previous = fold(chosen)
    return "".join(parts)


def canonicalise(text: str) -> str:
    """Reverse only the transformations this demo introduces, using the text alone.

    Deliberately fixture-independent: it never consults the original passage or a
    transform history, because a real detector-side canonicaliser does not
    receive the attacker's log. A deletion therefore stays unrecovered.
    """
    reject_lone_surrogates(text)
    without_zero_width = text.replace(ZERO_WIDTH_SPACE, "")
    return "".join(CONFUSABLES.get(c, c) for c in without_zero_width)


def describe_changes(before: str, after: str) -> list[str]:
    """Name the characters that differ, not just their positions.

    Two of the three perturbations are invisible or visually deceptive, so a
    rendered passage cannot communicate them and a bare index is useless.

    The comparison is aligned from both ends. A plain index-by-index walk
    reports every character after a single insertion as changed, because the
    tail has shifted, and never names a character that exists only in `after`.
    """
    head = 0
    limit = min(len(before), len(after))
    while head < limit and before[head] == after[head]:
        head += 1
    tail = 0
    while tail < limit - head and before[-1 - tail] == after[-1 - tail]:
        tail += 1
    removed = before[head:len(before) - tail]
    added = after[head:len(after) - tail]
    lines: list[str] = []
    for offset, character in enumerate(removed):
        lines.append(f"Position {head + offset}: removed {_name(character)}")
    for offset, character in enumerate(added):
        lines.append(f"Position {head + offset}: inserted {_name(character)}")
    return lines


def _name(character: str) -> str:
    try:
        return f"{unicodedata.name(character)}, U+{ord(character):04X}"
    except ValueError:
        return f"U+{ord(character):04X}"


def next_state(state: str, command: str) -> str:
    """Refuse any transition the state machine does not define."""
    try:
        return VALID_TRANSITIONS[(state, command)]
    except KeyError:
        raise DeclawdError(f"invalid transition: cannot {command} from state {state!r}") from None
