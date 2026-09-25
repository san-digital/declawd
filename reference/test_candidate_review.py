from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

import candidate_review
import declawd


class CandidateReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.template_path = Path(temporary.name) / "template.json"
        self.review_path = Path(temporary.name) / "review.json"
        self.template = {
            "segments": ["First sentence. ", ["Keep", "Retain"], " the ", ["sheet", "record"], ". Final sentence."]
        }
        self.write_template()
        self.review = {
            "schema": candidate_review.SCHEMA,
            "method": candidate_review.METHOD,
            "template_sha256": hashlib.sha256(self.template_path.read_bytes()).hexdigest(),
            "entries": [
                dict(variant, grammar_approved=True, same_job_approved=True, rationale="Both choices require keeping the written record.")
                for variant in candidate_review.render_variants(self.template_path)
            ],
        }
        self.write_review()

    def write_template(self) -> None:
        self.template_path.write_text(json.dumps(self.template) + "\n", encoding="utf-8")

    def write_review(self) -> None:
        self.review_path.write_text(json.dumps(self.review) + "\n", encoding="utf-8")

    def test_renders_each_candidate_in_its_complete_sentence(self) -> None:
        self.assertEqual(candidate_review.render_variants(self.template_path), [
            {"segment_index": 1, "candidate": "Keep", "sentence": "Keep the sheet."},
            {"segment_index": 1, "candidate": "Retain", "sentence": "Retain the sheet."},
            {"segment_index": 3, "candidate": "sheet", "sentence": "Keep the sheet."},
            {"segment_index": 3, "candidate": "record", "sentence": "Keep the record."},
        ])
        candidate_review.validate(self.template_path, self.review_path)

    def test_template_change_requires_a_fresh_review(self) -> None:
        self.template["segments"][2] = " the original "
        self.write_template()
        with self.assertRaisesRegex(ValueError, "stale"):
            candidate_review.validate(self.template_path, self.review_path)

    def test_updating_only_the_digest_does_not_approve_changed_sentences(self) -> None:
        self.template["segments"][2] = " the original "
        self.write_template()
        self.review["template_sha256"] = hashlib.sha256(self.template_path.read_bytes()).hexdigest()
        self.write_review()
        with self.assertRaisesRegex(ValueError, "sentence differs"):
            candidate_review.validate(self.template_path, self.review_path)

    def test_missing_and_duplicate_entries_are_rejected(self) -> None:
        original = copy.deepcopy(self.review)
        self.review["entries"].pop()
        self.write_review()
        with self.assertRaisesRegex(ValueError, "every candidate"):
            candidate_review.validate(self.template_path, self.review_path)
        self.review = original
        self.review["entries"][-1] = self.review["entries"][0]
        self.write_review()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            candidate_review.validate(self.template_path, self.review_path)

    def test_unknown_candidate_does_not_substitute_for_a_required_review(self) -> None:
        self.review["entries"][0]["candidate"] = "Archive"
        self.write_review()
        with self.assertRaisesRegex(ValueError, "missing"):
            candidate_review.validate(self.template_path, self.review_path)

    def test_each_approval_and_rationale_is_required(self) -> None:
        original = copy.deepcopy(self.review)
        for key, value in [("grammar_approved", False), ("same_job_approved", 1), ("rationale", " ")]:
            with self.subTest(key=key):
                self.review = copy.deepcopy(original)
                self.review["entries"][0][key] = value
                self.write_review()
                with self.assertRaises(ValueError):
                    candidate_review.validate(self.template_path, self.review_path)

    def test_slots_require_distinct_single_tokens_and_multiple_choices(self) -> None:
        for choices in [["Keep"], ["Keep", "keep"], ["Keep", "Hold on"], ["Keep", "Rétain"], ["Keep", 4]]:
            with self.subTest(choices=choices):
                self.template["segments"][1] = choices
                self.write_template()
                with self.assertRaises(ValueError):
                    candidate_review.render_variants(self.template_path)

    def test_candidate_must_be_a_separate_token_in_a_complete_sentence(self) -> None:
        self.template["segments"] = ["Please", ["keep", "retain"], " the sheet."]
        self.write_template()
        with self.assertRaisesRegex(ValueError, "adjacent token"):
            candidate_review.render_variants(self.template_path)
        self.template["segments"] = [["Keep", "Retain"], " the sheet"]
        self.write_template()
        with self.assertRaisesRegex(ValueError, "complete sentence"):
            candidate_review.render_variants(self.template_path)

    def test_committed_v2_review_and_seed_independent_length(self) -> None:
        template_path = ROOT / "fixtures" / "template-v2.json"
        candidate_review.validate(template_path, ROOT / "fixtures" / "candidate-review-v2.json")
        segments = json.loads(template_path.read_text(encoding="utf-8"))["segments"]
        default_text = "".join(segment if isinstance(segment, str) else segment[0] for segment in segments)
        self.assertGreater(declawd.count_contexts(default_text), 250)
        literal_text = "".join(segment for segment in segments if isinstance(segment, str))
        for word in ("clock", "pressure", "quality"):
            self.assertEqual(declawd.scan(literal_text).count(word), 1)


if __name__ == "__main__":
    unittest.main()
