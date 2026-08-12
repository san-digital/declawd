from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

import declawd


class PublishedVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        declawd.load_profile(ROOT / "fixtures" / "profile-v1.json")

    def test_scoring_vectors(self) -> None:
        document = json.loads((ROOT / "vectors" / "scoring-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(document["profile"]["profile_id"], "declawd-v1")
        for vector in document["vectors"]:
            with self.subTest(text=vector["text"][:24]):
                result = declawd.score(vector["text"])
                self.assertEqual(result.raw_tokens, vector["raw"])
                self.assertEqual(result.effective_tokens, vector["effective"])
                self.assertEqual(result.green, vector["green"])
                self.assertEqual(result.verdict, vector["verdict"])
                if vector["z"] is None:
                    self.assertIsNone(result.z_display)
                else:
                    self.assertAlmostEqual(result.z_display, vector["z"], places=14)

    def test_controlled_removal_steps(self) -> None:
        document = json.loads(
            (ROOT / "vectors" / "controlled-removal-v1.json").read_text(encoding="utf-8")
        )
        source = document["source_text"]
        substitutions = document["substitutions"]

        for index, step in enumerate(document["steps"], start=1):
            text = source
            for substitution in reversed(substitutions[:index]):
                offset = substitution["scalar_offset"]
                before = substitution["before"]
                after = substitution["after"]
                self.assertEqual(text[offset:offset + len(before)], before)
                text = text[:offset] + after + text[offset + len(before):]
            result = declawd.score(text)
            expected = step["score"]
            self.assertEqual(result.raw_tokens, expected["raw"])
            self.assertEqual(result.effective_tokens, expected["effective"])
            self.assertEqual(result.green, expected["green"])
            self.assertEqual(result.verdict, expected["verdict"])
            self.assertAlmostEqual(result.z_display, expected["z"], places=14)

        self.assertEqual(text, document["expected_text"])
        self.assertEqual(result.effective_tokens, 358)
        self.assertEqual(result.green, 102)
        self.assertAlmostEqual(result.z_display, 1.5256954942433834, places=14)


if __name__ == "__main__":
    unittest.main()
