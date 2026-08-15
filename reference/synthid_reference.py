#!/usr/bin/env python3
"""Standard-library reference for the Declawd SynthID teaching contracts."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
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
SAMPLING_TABLE_SEED = 0
SAMPLING_TABLE_SHA256 = "4b2efa3fbbaa5f77facce45f2c2af38ba36436b2b2b81f950005fa8af266fd3c"
DEPTH = 30
KEYS = (654, 400, 836, 123, 340, 443, 597, 160, 57, 29, 590, 639,
        13, 715, 468, 990, 966, 226, 324, 585, 118, 504, 421, 521,
        129, 669, 732, 225, 90, 960)
MULTIPLIER = 6_364_136_223_846_793_005
MASK_64 = 2**64 - 1
WEIGHT_SUM = 4_785
MAX_CANDIDATE_CONTEXTS = 99_996
MAX_G_BITS = 2_999_880
MAX_G_BYTES = 374_985
MAX_MASK_BYTES = 12_500
MAX_WEIGHTED_SUM = 478_480_860
WEIGHTS = (290, 281, 272, 263, 254, 245, 236, 227, 218, 209, 200,
           191, 182, 173, 164, 155, 146, 137, 128, 119, 110, 101, 92,
           83, 74, 65, 56, 47, 38, 29)
WARNINGS = [
    "public-reference-profile-only",
    "no-detector-threshold-or-authorship-verdict",
]


class ExpectedMismatch(RuntimeError):
    """A structurally valid expected result differs from the derived result."""


def reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def parse_strict_json_bytes(source: bytes) -> Any:
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("trace must be strict UTF-8 JSON without a BOM") from error
    if text.startswith("\ufeff"):
        raise ValueError("trace must be strict UTF-8 JSON without a BOM")
    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_object_pairs,
        parse_constant=reject_non_finite_constant,
    )


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


def load_sampling_table(
    path: Path = ROOT / "fixtures/synthid/sampling-table-v1.bin",
) -> bytes:
    table = path.read_bytes()
    if len(table) != TABLE_SIZE // 8:
        raise ValueError("committed sampling table has the wrong length")
    if hashlib.sha256(table).hexdigest() != SAMPLING_TABLE_SHA256:
        raise ValueError("committed sampling table has the wrong SHA-256")
    return table


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


def require_integer(value: Any, minimum: int, maximum: int, name: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"expected.{name} is out of range")


def validate_digest(value: Any, max_bits: int, max_bytes: int, name: str) -> None:
    if not isinstance(value, dict) or set(value) != {
        "bit_length", "byte_length", "sha256"
    }:
        raise ValueError(f"expected.{name} is not a digest")
    require_integer(value["bit_length"], 0, max_bits, f"{name}.bit_length")
    require_integer(value["byte_length"], 0, max_bytes, f"{name}.byte_length")
    if not isinstance(value["sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["sha256"]
    ):
        raise ValueError(f"expected.{name}.sha256 is invalid")


def validate_fraction(value: Any, maximum: int, name: str) -> None:
    if not isinstance(value, dict) or set(value) != {
        "numerator", "denominator", "decimal"
    }:
        raise ValueError(f"expected.{name} is not an exact fraction")
    require_integer(value["numerator"], 0, maximum, f"{name}.numerator")
    require_integer(value["denominator"], 1, maximum, f"{name}.denominator")
    decimal = value["decimal"]
    if not isinstance(decimal, str) or not re.fullmatch(
        r"(?:0\.[0-9]{12}|1\.000000000000)", decimal
    ):
        raise ValueError(f"expected.{name}.decimal is invalid")


def validate_expected(value: Any) -> None:
    required = {
        "status", "token_count", "candidate_context_count", "first_eos_index",
        "repetition_excluded_count", "eos_excluded_count",
        "valid_context_count", "g_value_one_count", "weighted_g_value_sum",
        "g_values", "masks", "raw_score", "weighted_score",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("expected must be an exact v1 expected-result object")
    if value["status"] not in ("scored", "insufficient_data"):
        raise ValueError("expected.status is invalid")
    require_integer(value["token_count"], 0, TOKEN_LIMIT, "token_count")
    for name in (
        "candidate_context_count", "repetition_excluded_count",
        "eos_excluded_count", "valid_context_count",
    ):
        require_integer(value[name], 0, MAX_CANDIDATE_CONTEXTS, name)
    first_eos = value["first_eos_index"]
    if first_eos is not None:
        require_integer(first_eos, 0, 99_999, "first_eos_index")
    require_integer(value["g_value_one_count"], 0, MAX_G_BITS, "g_value_one_count")
    require_integer(
        value["weighted_g_value_sum"], 0, MAX_WEIGHTED_SUM,
        "weighted_g_value_sum",
    )
    validate_digest(value["g_values"], MAX_G_BITS, MAX_G_BYTES, "g_values")
    masks = value["masks"]
    if not isinstance(masks, dict) or set(masks) != {"repetition", "eos", "valid"}:
        raise ValueError("expected.masks is invalid")
    for name in ("repetition", "eos", "valid"):
        validate_digest(
            masks[name], MAX_CANDIDATE_CONTEXTS, MAX_MASK_BYTES, f"masks.{name}"
        )
    if value["status"] == "scored":
        if value["valid_context_count"] == 0:
            raise ValueError("expected scored result requires valid contexts")
        validate_fraction(value["raw_score"], MAX_G_BITS, "raw_score")
        validate_fraction(
            value["weighted_score"], MAX_WEIGHTED_SUM, "weighted_score"
        )
    elif (
        value["valid_context_count"] != 0
        or value["raw_score"] is not None
        or value["weighted_score"] is not None
    ):
        raise ValueError(
            "expected insufficient_data result requires zero valid contexts and null scores"
        )


def score_trace(trace: dict[str, Any], source_bytes: bytes) -> dict[str, Any]:
    if not isinstance(trace, dict):
        raise ValueError("trace must be a JSON object")
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
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in tokenizer[field])
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
    if "expected" in trace:
        validate_expected(trace["expected"])

    table = load_sampling_table()
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
                weighted_numerator += WEIGHTS[depth]

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
    if "expected" in trace and trace["expected"] != expected_from_report(report):
        raise ExpectedMismatch("trace expected result does not match the computed score")
    return report


def load_and_score(path: Path) -> dict[str, Any]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"symlink inputs are refused: {path}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"trace input must be a regular file: {path}")
        if opened.st_size > TRACE_LIMIT:
            raise ValueError(f"trace exceeds the {TRACE_LIMIT}-byte limit")
        chunks = []
        remaining = TRACE_LIMIT + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        source = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(source) > TRACE_LIMIT:
        raise ValueError(f"trace exceeds the {TRACE_LIMIT}-byte limit")
    return score_trace(parse_strict_json_bytes(source), source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    try:
        document = load_and_score(args.trace)
    except ExpectedMismatch as error:
        print(f"declawd synthid reference: {error}", file=sys.stderr)
        return 3
    except (OSError, ValueError, RecursionError) as error:
        print(f"declawd synthid reference: {error}", file=sys.stderr)
        return 2
    report = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    sys.stdout.buffer.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
