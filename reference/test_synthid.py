#!/usr/bin/env python3
"""Tests for the exact standard-library SynthID teaching reference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthid_reference as reference


class SynthIdReferenceTest(unittest.TestCase):
    def load(self, name: str) -> tuple[dict, bytes]:
        data = (ROOT / "fixtures/synthid" / name).read_bytes()
        return json.loads(data), data

    def test_prepared_vector(self) -> None:
        trace, source = self.load("trace-prepared-v1.json")
        report = reference.score_trace(trace, source)
        self.assertEqual(report["valid_context_count"], 8)
        self.assertEqual(report["raw_score"]["decimal"], "0.545833333333")
        self.assertEqual(report["weighted_score"]["decimal"], "0.518443051202")

    def test_eos_and_repetition_masks(self) -> None:
        eos, source = self.load("trace-eos-v1.json")
        self.assertEqual(reference.score_trace(eos, source)["valid_context_count"], 2)
        repeated, source = self.load("trace-repeated-v1.json")
        report = reference.score_trace(repeated, source)
        self.assertEqual(report["valid_context_count"], 5)
        self.assertEqual(
            report["masks"]["repetition"]["sha256"],
            "ffe679bb831c95b67dc17819c63c5090d221aac6f4c7bf530f594ab43d21fa1e",
        )

    def test_short_trace_is_insufficient_without_nan(self) -> None:
        trace, source = self.load("trace-short-v1.json")
        report = reference.score_trace(trace, source)
        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["raw_score"])
        self.assertIsNone(report["weighted_score"])
        self.assertEqual(
            report["g_values"]["sha256"],
            hashlib.sha256(b"").hexdigest(),
        )

    def test_wrapping_hash_and_half_even(self) -> None:
        value = reference.accumulate_hash(1, [2**32 - 1, 2, 3, 4, 5])
        self.assertLess(value, 0)
        self.assertEqual(value % 65_536, 16_035)
        self.assertEqual(reference.round_half_even(1, 8, 2), "0.12")
        self.assertEqual(reference.round_half_even(3, 8, 2), "0.38")

    def test_distribution_g_values_are_derived_from_the_profile(self) -> None:
        distribution, _ = self.load("distribution-v1.json")
        table = (ROOT / "fixtures/synthid/sampling-table-v1.bin").read_bytes()
        rows = []
        for candidate in distribution["candidates"]:
            ngram = distribution["context_token_ids"] + [candidate["token_id"]]
            ngram_hash = reference.accumulate_hash(1, ngram)
            row = []
            for key in reference.KEYS:
                index = reference.accumulate_hash(ngram_hash, (key,)) % 65_536
                row.append((table[index // 8] >> (index % 8)) & 1)
            rows.append(row)
        self.assertEqual(rows, distribution["g_values"])
        self.assertEqual(
            sum(candidate["mass_numerator"] for candidate in distribution["candidates"]),
            distribution["mass_denominator"],
        )
        ids = [candidate["id"] for candidate in distribution["candidates"]]
        token_ids = [candidate["token_id"] for candidate in distribution["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(token_ids), len(set(token_ids)))
        by_id = {candidate["id"]: index for index, candidate in enumerate(distribution["candidates"])}
        seen_depths = set()
        for draw in distribution["draws"]:
            self.assertIn(draw["first"], by_id)
            self.assertIn(draw["second"], by_id)
            self.assertIn(draw["winner"], (draw["first"], draw["second"]))
            self.assertNotIn(draw["depth"], seen_depths)
            seen_depths.add(draw["depth"])
            first = by_id[draw["first"]]
            second = by_id[draw["second"]]
            expected = first if rows[first][draw["depth"]] >= rows[second][draw["depth"]] else second
            self.assertEqual(draw["winner"], ids[expected])

    def test_sampling_table_and_nature_pdf_are_pinned(self) -> None:
        table = (ROOT / "fixtures/synthid/sampling-table-v1.bin").read_bytes()
        self.assertEqual(len(table), 8192)
        self.assertEqual(
            hashlib.sha256(table).hexdigest(),
            "4b2efa3fbbaa5f77facce45f2c2af38ba36436b2b2b81f950005fa8af266fd3c",
        )
        paper = (ROOT / "evidence/synthid/dathathri-2024-synthid-text.pdf").read_bytes()
        self.assertEqual(len(paper), 4_313_074)
        self.assertEqual(
            hashlib.sha256(paper).hexdigest(),
            "ac88f69c1af9f9748cfb0b10ea34b5a0b0329bc4461cb6a57442ce572a678a4e",
        )

    def test_trace_rejects_prose_and_expected_mismatch(self) -> None:
        trace, source = self.load("trace-short-v1.json")
        trace["text"] = "not accepted"
        with self.assertRaisesRegex(ValueError, "unknown trace fields"):
            reference.score_trace(trace, source)
        trace, source = self.load("trace-prepared-v1.json")
        trace["expected"]["raw_score"]["numerator"] -= 1
        with self.assertRaisesRegex(RuntimeError, "expected result"):
            reference.score_trace(trace, source)

    def test_tokenizer_metadata_uses_the_schema_character_limit(self) -> None:
        trace, source = self.load("trace-short-v1.json")
        trace["tokenizer"]["model_id"] = "é" * 256
        reference.score_trace(trace, source)
        trace["tokenizer"]["model_id"] += "é"
        with self.assertRaisesRegex(ValueError, "1 to 256 characters"):
            reference.score_trace(trace, source)


if __name__ == "__main__":
    unittest.main()
