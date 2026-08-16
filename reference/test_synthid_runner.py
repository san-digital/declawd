#!/usr/bin/env python3
"""Input-boundary tests for the optional token-only model runner."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthid_model_runner as runner


class SynthIdRunnerInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (ROOT / "fixtures/synthid/gpt2-input-v1.json").read_text()
        )
        self.spec = runner.MODELS["gpt2"]

    def validate(self, document: dict) -> list[int]:
        return runner.validate_input(document, "gpt2", self.spec)

    def test_pinned_input_is_accepted(self) -> None:
        self.assertEqual(self.validate(self.document), self.document["prompt_token_ids"])

    def test_unknown_and_missing_fields_are_rejected(self) -> None:
        self.document["text"] = "not accepted"
        with self.assertRaisesRegex(ValueError, "exactly"):
            self.validate(self.document)
        self.document.pop("text")
        self.document.pop("revision")
        with self.assertRaisesRegex(ValueError, "exactly"):
            self.validate(self.document)

    def test_schema_model_repository_and_revision_are_pinned(self) -> None:
        for field, value in (
            ("schema", "declawd.synthid-model-input/v2"),
            ("model", "gemma-2b-it"),
            ("repository", "untrusted/model"),
            ("revision", "main"),
        ):
            changed = dict(self.document)
            changed[field] = value
            with self.assertRaises(ValueError, msg=field):
                self.validate(changed)

    def test_prompt_ids_reject_bool_float_negative_empty_and_oversize(self) -> None:
        for token_ids in ([True], [1.5], [-1], [], [0] * 100_001):
            changed = dict(self.document)
            changed["prompt_token_ids"] = token_ids
            with self.assertRaisesRegex(ValueError, "prompt_token_ids"):
                self.validate(changed)

    def test_prompt_ids_must_fit_the_loaded_vocabulary(self) -> None:
        runner.validate_vocabulary([0, 50_256], 50_257)
        with self.assertRaisesRegex(ValueError, "vocabulary size 50257"):
            runner.validate_vocabulary([50_257], 50_257)

    def test_loader_rejects_duplicate_fields_and_non_standard_encoding(self) -> None:
        source = (ROOT / "fixtures/synthid/gpt2-input-v1.json").read_bytes()
        duplicate = source.decode().replace(
            '"model": "gpt2"',
            '"model": "gpt2",\n  "model": "gpt2"',
            1,
        ).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            for changed in (duplicate, b"\xef\xbb\xbf" + source):
                path.write_bytes(changed)
                with self.assertRaises(ValueError):
                    runner.load_input(path, "gpt2", self.spec)

    def test_watermark_parameters_use_the_canonical_profile_constants(self) -> None:
        self.assertEqual(
            runner.watermark_parameters(),
            {
                "ngram_len": runner.NGRAM_LEN,
                "keys": list(runner.KEYS),
                "context_history_size": runner.CONTEXT_HISTORY_SIZE,
                "sampling_table_seed": runner.SAMPLING_TABLE_SEED,
                "sampling_table_size": runner.TABLE_SIZE,
            },
        )


if __name__ == "__main__":
    unittest.main()
