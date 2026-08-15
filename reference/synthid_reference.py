#!/usr/bin/env python3
"""Standard-library reference for the Declawd SynthID teaching contracts."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "declawd.synthid-profile/v1"
PROFILE_SHA256 = "3fcb8947cc6e267a653196571d9e43434de405b2977838cf95167c94c0ac8e08"
TRACE_SCHEMA = "declawd.synthid-trace/v1"
SCORE_SCHEMA = "declawd.synthid-score/v1"
TRACE_LIMIT = 8 * 1024 * 1024
TOKEN_LIMIT = 100_000
TOKEN_ID_MAX = 2_147_483_647
NGRAM_LEN = 5
CONTEXT_HISTORY_SIZE = 1024
TABLE_SIZE = 65_536
DEPTH = 30
KEYS = (654, 400, 836, 123, 340, 443, 597, 160, 57, 29, 590, 639,
        13, 715, 468, 990, 966, 226, 324, 585, 118, 504, 421, 521,
        129, 669, 732, 225, 90, 960)
MULTIPLIER = 6_364_136_223_846_793_005
MASK_64 = 2**64 - 1
WEIGHT_SUM = 4_785
WARNINGS = [
    "public-reference-profile-only",
    "no-detector-threshold-or-authorship-verdict",
]


def signed_i64(value: int) -> int:
    value &= MASK_64
    return value - 2**64 if value >= 2**63 else value


def accumulate_hash(current: int, data: list[int] | tuple[int, ...]) -> int:
    for value in data:
        current = signed_i64((current + value) * MULTIPLIER + 1)
    return current


def pack_lsb0(bits: list[bool]) -> bytes:
    packed = bytearray((len(bits) + 7) // 8)
    for index, bit in enumerate(bits):
        if bit:
            packed[index // 8] |= 1 << (index % 8)
    return bytes(packed)


def digest(bits: list[bool]) -> dict[str, Any]:
    packed = pack_lsb0(bits)
    return {
        "bit_length": len(bits),
        "byte_length": len(packed),
        "sha256": hashlib.sha256(packed).hexdigest(),
    }


def round_half_even(numerator: int, denominator: int, places: int = 12) -> str:
    scale = 10**places
    quotient, remainder = divmod(numerator * scale, denominator)
    if remainder * 2 > denominator or (
        remainder * 2 == denominator and quotient % 2 == 1
    ):
        quotient += 1
    integer, fraction = divmod(quotient, scale)
    return f"{integer}.{fraction:0{places}d}"


def exact_score(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "decimal": round_half_even(numerator, denominator),
    }


def expected_from_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report[key]
        for key in (
            "status", "token_count", "valid_context_count",
            "candidate_context_count", "first_eos_index",
            "repetition_excluded_count", "eos_excluded_count",
            "g_value_one_count", "weighted_g_value_sum",
            "g_values", "masks", "raw_score", "weighted_score",
        )
    }


def score_trace(trace: dict[str, Any], source_bytes: bytes) -> dict[str, Any]:
    allowed = {
        "schema", "trace_id", "profile", "sequence_role", "tokenizer",
        "token_ids", "expected",
    }
    if set(trace) - allowed:
        raise ValueError(f"unknown trace fields: {sorted(set(trace) - allowed)}")
    if trace.get("schema") != TRACE_SCHEMA:
        raise ValueError(f"trace schema must be {TRACE_SCHEMA}")
    if trace.get("profile") != {"id": PROFILE_ID, "file_sha256": PROFILE_SHA256}:
        raise ValueError("trace profile reference is not the pinned public profile")
    trace_id = trace.get("trace_id")
    if (
        not isinstance(trace_id, str)
        or not 1 <= len(trace_id) <= 128
        or any(not (character.isascii() and (character.islower() or character.isdigit() or character == "-")) for character in trace_id)
    ):
        raise ValueError("trace_id must use lowercase ASCII letters, digits or hyphens")
    if trace.get("sequence_role") != "generated_output_only":
        raise ValueError("sequence_role must be generated_output_only")
    tokenizer = trace.get("tokenizer")
    if not isinstance(tokenizer, dict) or set(tokenizer) != {"model_id", "revision", "eos_token_id"}:
        raise ValueError("tokenizer metadata is incomplete or has unknown fields")
    if not all(
        isinstance(tokenizer.get(field), str)
        and 1 <= len(tokenizer[field]) <= 256
        for field in ("model_id", "revision")
    ):
        raise ValueError("tokenizer model_id and revision must contain 1 to 256 characters")
    tokens = trace.get("token_ids")
    if not isinstance(tokens, list) or len(tokens) > TOKEN_LIMIT:
        raise ValueError(f"token_ids must be an array of at most {TOKEN_LIMIT} items")
    if any(type(token) is not int or token < 0 or token > TOKEN_ID_MAX for token in tokens):
        raise ValueError(f"token IDs must be integers from 0 to {TOKEN_ID_MAX}")
    eos_id = tokenizer.get("eos_token_id")
    if eos_id is not None and (
        type(eos_id) is not int or eos_id < 0 or eos_id > TOKEN_ID_MAX
    ):
        raise ValueError("eos_token_id must be null or a valid token ID")

    table = (ROOT / "fixtures/synthid/sampling-table-v1.bin").read_bytes()
    if len(table) != TABLE_SIZE // 8:
        raise ValueError("committed sampling table has the wrong length")
    candidate_context_count = max(0, len(tokens) - (NGRAM_LEN - 1))
    first_eos = tokens.index(eos_id) if eos_id is not None and eos_id in tokens else None
    history = deque([0] * CONTEXT_HISTORY_SIZE, maxlen=CONTEXT_HISTORY_SIZE)
    history_counts = Counter({0: CONTEXT_HISTORY_SIZE})
    repetitions: list[bool] = []
    eos_mask: list[bool] = []
    valid_mask: list[bool] = []
    g_values: list[bool] = []
    raw_numerator = 0
    weighted_numerator = 0
    valid_count = 0

    for position in range(candidate_context_count):
        context_hash = accumulate_hash(1, tokens[position:position + NGRAM_LEN - 1])
        repetition_bit = context_hash not in history_counts
        evicted = history[-1]
        history.appendleft(context_hash)
        history_counts[context_hash] += 1
        history_counts[evicted] -= 1
        if history_counts[evicted] == 0:
            del history_counts[evicted]
        eos_bit = first_eos is None or position + NGRAM_LEN - 1 < first_eos
        valid_bit = repetition_bit and eos_bit
        repetitions.append(repetition_bit)
        eos_mask.append(eos_bit)
        valid_mask.append(valid_bit)
        valid_count += int(valid_bit)

        ngram_hash = accumulate_hash(1, tokens[position:position + NGRAM_LEN])
        for depth, key in enumerate(KEYS):
            keyed_hash = accumulate_hash(ngram_hash, (key,))
            index = keyed_hash % TABLE_SIZE
            g = bool((table[index // 8] >> (index % 8)) & 1)
            g_values.append(g)
            if valid_bit and g:
                raw_numerator += 1
                weighted_numerator += 290 - 9 * depth

    report: dict[str, Any] = {
        "schema": SCORE_SCHEMA,
        "trace_id": trace_id,
        "profile": trace["profile"],
        "trace_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "status": "scored" if valid_count else "insufficient_data",
        "token_count": len(tokens),
        "candidate_context_count": candidate_context_count,
        "first_eos_index": first_eos,
        "repetition_excluded_count": repetitions.count(False),
        "eos_excluded_count": eos_mask.count(False),
        "valid_context_count": valid_count,
        "g_value_one_count": raw_numerator,
        "weighted_g_value_sum": weighted_numerator,
        "g_values": digest(g_values),
        "masks": {
            "repetition": digest(repetitions),
            "eos": digest(eos_mask),
            "valid": digest(valid_mask),
        },
        "raw_score": exact_score(raw_numerator, DEPTH * valid_count) if valid_count else None,
        "weighted_score": exact_score(weighted_numerator, WEIGHT_SUM * valid_count) if valid_count else None,
        "warnings": WARNINGS,
    }
    expected = trace.get("expected")
    if expected is not None and expected != expected_from_report(report):
        raise RuntimeError("trace expected result does not match the computed score")
    return report


def load_and_score(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"symlink inputs are refused: {path}")
    size = path.stat().st_size
    if size > TRACE_LIMIT:
        raise ValueError(f"trace exceeds the {TRACE_LIMIT}-byte limit")
    source = path.read_bytes()
    return score_trace(json.loads(source), source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(load_and_score(args.trace), indent=2) + "\n", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
