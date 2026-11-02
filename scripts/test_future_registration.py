from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import future_candidate_review as review
import future_registration as guard

SCRIPTS = Path(__file__).resolve().parent


def words(count: int) -> str:
    return " ".join("word" + chr(97 + index // 26) + chr(97 + index % 26) for index in range(count))


def json_file(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(guard.encoded(value))


def write_review(root: Path) -> None:
    path = root / "fixtures/template.json"
    json_file(root / "fixtures/review.json", {
        "schema": review.SCHEMA, "method": review.METHOD,
        "template_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "article_sounds": {},
        "entries": [{**variant, "grammar_approved": True, "same_job_approved": True, "rationale": "Synthetic token-boundary control."} for variant in review.render_variants(path)],
    })


class BoundaryTests(unittest.TestCase):
    def test_split_literal_tokens_are_coalesced_before_counting(self):
        segments = ["a", "bc a", "bc ab", "c abc", " abc ", ["plain", "simple"], "."]
        self.assertEqual(guard.literal_bound(segments), 2)
        self.assertEqual(guard.literal_bound(["abc abc abc abc ", ["plain", "simple"], "."]), 2)

    def test_split_apostrophes_preserve_the_exact_scanner(self):
        self.assertEqual(guard.literal_bound(["can", "'", "t can't ", ["plain", "simple"], "."]), 2)
        self.assertEqual(guard.count_contexts("can't can't"), 2)
        self.assertEqual(guard.count_contexts("can’t can’t"), 3)

    def test_every_variable_boundary_needs_a_separator(self):
        cases = [
            ["join", ["plain", "simple"], "."],
            ["join'", ["plain", "simple"], "."],
            ["join ", ["plain", "simple"], "tail"],
            ["join ", ["plain", "simple"], "'tail"],
            [["plain", "simple"], ["clean", "clear"]],
            ["join", "", ["plain", "simple"], "."],
        ]
        for segments in cases:
            with self.subTest(segments=segments), self.assertRaisesRegex(ValueError, "token separator"):
                guard.literal_bound(segments)

    def test_bound_survives_each_complete_candidate_combination(self):
        import itertools
        segments = ["Start with can't ", ["plain", "simple"], ". Keep stable words and ", ["clean", "clear"], " text."]
        bound = guard.literal_bound(segments)
        for first, second in itertools.product(segments[1], segments[3]):
            self.assertGreaterEqual(guard.count_contexts(segments[0] + first + segments[2] + second + segments[4]), bound)


    def test_recorded_v3_bound_remains_safe_without_changing_its_registration(self):
        root = SCRIPTS.parent / "experiments/declawd-v3"
        template = json.loads((root / "fixtures/template-v3.json").read_bytes())
        registration = json.loads((root / "fixtures/registration-v3.json").read_bytes())
        self.assertEqual(registration["marked_effective_token_lower_bound"], 286)
        self.assertEqual(guard.literal_bound(template["segments"]), 290)

    def test_public_review_pins_the_current_guard_sources(self):
        root = SCRIPTS.parent
        report = json.loads((root / "reports/future-registration-review-2026-11-02.json").read_bytes())
        self.assertFalse(report["new_experiment_created"])
        self.assertFalse(report["actual_seed_drawn"])
        for name, digest in report["source_files"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)



class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="declawd-future-registration-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.root = self.repo / "experiments/next"
        self.root.mkdir(parents=True)
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        patch = mock.patch.dict(os.environ, self.environment, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        for name in guard.ENGINE_FILES:
            path = self.repo / "scripts" / name
            path.parent.mkdir(exist_ok=True)
            shutil.copyfile(SCRIPTS / name, path)
        spec = importlib.util.spec_from_file_location("isolated_future_registration", self.repo / "scripts/future_registration.py")
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)
        self.configuration = {
            "profile_id": "declawd-v4", "template": "fixtures/template.json", "review": "fixtures/review.json",
            "corpus": "fixtures/corpus.json", "minimum_effective_tokens": 200, "inputs": ["plan.md", "score.py"],
            "registration": "fixtures/registration.json", "seed": "fixtures/seed.json", "outputs": ["reports/calibration.json", "reports/evaluation.json"],
        }
        json_file(self.root / "experiment.json", self.configuration)
        json_file(self.root / "fixtures/template.json", {"fixture_id": "synthetic", "segments": [words(210) + ". The result is ", ["plain", "simple"], "."]})
        write_review(self.root)
        json_file(self.root / "fixtures/corpus.json", {"passages": [{"id": name, "author": name, "split": name, "text": words(220)} for name in ("calibration", "evaluation")]})
        (self.root / "plan.md").write_text("Synthetic protocol test.\n")
        (self.root / "score.py").write_text("pass\n")
        self.git("init", "--quiet")
        self.commit()

    def git(self, *arguments):
        return subprocess.check_output(["git", "-c", "user.name=Protocol Test", "-c", "user.email=protocol@example.invalid", "-c", "maintenance.auto=false", "-c", "gc.auto=0", *arguments], cwd=self.repo, stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "--no-verify", "--quiet", "-m", "freeze synthetic inputs")

    def register(self):
        return self.guard.register(self.root, "experiment.json")

    def registered(self):
        receipt = self.register()
        self.commit()
        return receipt

    def sampled(self):
        self.registered()
        with mock.patch.object(self.guard.secrets, "token_bytes", return_value=b"\x11" * 32) as draw:
            seed = self.guard.sample(self.root, "experiment.json")
        draw.assert_called_once_with(32)
        self.commit()
        return seed

    def test_split_token_case_cannot_reach_registration_or_draw(self):
        word = "x" * 210
        text = (" " + word) * 205
        cuts = [(index - 1) * 211 + 1 + index for index in range(1, 204)]
        parts = []
        start = 0
        for cut in cuts:
            parts.append(text[start:cut])
            start = cut
        parts.extend([text[start:], " " + words(195) + " repeat repeat ", ["unique", "repeat"], " repeat."])
        json_file(self.root / "fixtures/template.json", {"fixture_id": "split-boundary", "segments": parts})
        write_review(self.root)
        with mock.patch.object(self.guard.secrets, "token_bytes") as draw, self.assertRaisesRegex(ValueError, "guaranteed literal pairs"):
            self.register()
        draw.assert_not_called()
        self.assertEqual(self.guard.literal_bound(parts), 199)
        self.assertEqual(self.guard.count_contexts("".join(part if isinstance(part, str) else part[0] for part in parts)), 201)

    def test_receipt_binds_config_inputs_review_tools_and_true_bound(self):
        receipt = self.registered()
        self.assertEqual(receipt["domain_separator"], "declawd/v4/green")
        self.assertGreaterEqual(receipt["guaranteed_literal_pairs"], 201)
        self.assertIn("scripts/future_registration.py", receipt["source_files"])
        self.assertIn("scripts/future_candidate_review.py", receipt["source_files"])
        self.assertIn("scripts/test_future_registration.py", receipt["source_files"])
        self.assertIn("experiments/next/experiment.json", receipt["source_files"])
        self.guard.verify_receipt(self.root, "experiment.json")

    def test_uncommitted_or_staged_nested_inputs_prevent_registration(self):
        path = self.root / "score.py"
        original = path.read_bytes()
        path.write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "commit the exact"):
            self.register()
        self.git("add", ".")
        path.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "staged changes"):
            self.register()

    def test_uncommitted_receipt_and_changed_tools_prevent_entropy(self):
        self.register()
        with mock.patch.object(self.guard.secrets, "token_bytes") as draw, self.assertRaises(subprocess.CalledProcessError):
            self.guard.sample(self.root, "experiment.json")
        draw.assert_not_called()
        self.commit()
        (self.repo / "scripts/future_registration.py").write_bytes(b"changed\n")
        with mock.patch.object(self.guard.secrets, "token_bytes") as draw, self.assertRaisesRegex(ValueError, "bound inputs changed"):
            self.guard.sample(self.root, "experiment.json")
        draw.assert_not_called()

    def test_one_draw_requires_seed_and_attempt_commit_before_outputs(self):
        self.registered()
        with mock.patch.object(self.guard.secrets, "token_bytes", return_value=b"\x11" * 32) as draw:
            self.guard.sample(self.root, "experiment.json")
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.guard.sample(self.root, "experiment.json")
            with self.assertRaises(subprocess.CalledProcessError):
                self.guard.verified_seed(self.root, "experiment.json")
        draw.assert_called_once_with(32)
        self.commit()
        self.guard.verified_seed(self.root, "experiment.json")

    def test_failed_seed_publication_leaves_attempt_and_blocks_another_draw(self):
        self.registered()
        original = self.guard.atomic_json
        def write(path, value, **options):
            if path.name == "seed.json":
                raise OSError("interrupted seed publication")
            original(path, value, **options)
        with mock.patch.object(self.guard, "atomic_json", side_effect=write), mock.patch.object(self.guard.secrets, "token_bytes", return_value=b"\x11" * 32) as draw:
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.guard.sample(self.root, "experiment.json")
        draw.assert_called_once_with(32)
        self.assertTrue((self.root / "fixtures/seed.json.attempt.json").exists())
        self.assertFalse((self.root / "fixtures/seed.json").exists())
        with mock.patch.object(self.guard.secrets, "token_bytes") as retry, self.assertRaisesRegex(ValueError, "already exists"):
            self.guard.sample(self.root, "experiment.json")
        retry.assert_not_called()

    def test_changed_receipt_is_rejected_before_entropy(self):
        self.registered()
        path = self.root / "fixtures/registration.json"
        receipt = json.loads(path.read_bytes())
        receipt["guaranteed_literal_pairs"] += 1
        json_file(path, receipt)
        self.commit()
        with mock.patch.object(self.guard.secrets, "token_bytes") as draw, self.assertRaisesRegex(ValueError, "bound inputs changed"):
            self.guard.sample(self.root, "experiment.json")
        draw.assert_not_called()

    def test_attempt_publication_precedes_entropy(self):
        self.registered()
        with mock.patch.object(self.guard, "atomic_json", side_effect=OSError("interrupted attempt publication")), mock.patch.object(self.guard.secrets, "token_bytes") as draw:
            with self.assertRaisesRegex(OSError, "interrupted attempt"):
                self.guard.sample(self.root, "experiment.json")
        draw.assert_not_called()

    def test_existing_output_prevents_entropy(self):
        self.registered()
        json_file(self.root / "reports/evaluation.json", {})
        with mock.patch.object(self.guard.secrets, "token_bytes") as draw, self.assertRaisesRegex(ValueError, "already exists"):
            self.guard.sample(self.root, "experiment.json")
        draw.assert_not_called()

    def test_registered_profile_identifier_cannot_be_reused(self):
        json_file(self.repo / "old/registration.json", {"registration_id": "declawd-v4"})
        self.commit()
        with self.assertRaisesRegex(ValueError, "already has a tracked registration"):
            self.register()

    def test_missing_fixture_and_invalid_corpus_fail_before_entropy(self):
        template_path = self.root / "fixtures/template.json"
        template = json.loads(template_path.read_bytes())
        template.pop("fixture_id")
        json_file(template_path, template)
        with self.assertRaisesRegex(ValueError, "fixture_id"):
            self.register()
        template["fixture_id"] = "restored"
        json_file(template_path, template)
        write_review(self.root)
        corpus_path = self.root / "fixtures/corpus.json"
        corpus = json.loads(corpus_path.read_bytes())
        corpus["passages"][1]["author"] = "calibration"
        json_file(corpus_path, corpus)
        with self.assertRaisesRegex(ValueError, "separate calibration"):
            self.register()

    def test_seed_rewritten_after_first_commit_is_rejected(self):
        self.sampled()
        path = self.root / "fixtures/seed.json"
        seed = json.loads(path.read_bytes())
        seed["seed_hex"] = "22" * 32
        json_file(path, seed)
        self.commit()
        with self.assertRaisesRegex(ValueError, "first committed draw"):
            self.guard.verified_seed(self.root, "experiment.json")

    def test_every_surviving_output_binding_is_checked_before_writes(self):
        self.sampled()
        value, _, binding = self.guard.verified_seed(self.root, "experiment.json")
        documents = {name: {**binding, "result": name} for name in value["outputs"]}
        self.guard.write_outputs(self.root, "experiment.json", documents)
        bad = copy.deepcopy(documents[value["outputs"][1]])
        bad["seed_hex"] = "22" * 32
        json_file(self.root / value["outputs"][1], bad)
        (self.root / value["outputs"][0]).unlink()
        with mock.patch.object(self.guard, "atomic_json") as write, self.assertRaisesRegex(ValueError, "surviving output"):
            self.guard.write_outputs(self.root, "experiment.json", documents)
        write.assert_not_called()

    def test_atomic_output_interruption_preserves_previous_complete_bytes(self):
        self.sampled()
        value, _, binding = self.guard.verified_seed(self.root, "experiment.json")
        documents = {name: {**binding, "result": name} for name in value["outputs"]}
        self.guard.write_outputs(self.root, "experiment.json", documents)
        path = self.root / value["outputs"][0]
        previous = path.read_bytes()
        with mock.patch.object(self.guard.os, "replace", side_effect=OSError("interrupted")), self.assertRaisesRegex(OSError, "interrupted"):
            self.guard.write_outputs(self.root, "experiment.json", documents)
        self.assertEqual(path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
