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

import calibrate_v3 as protocol
import candidate_review
import declawd

ROOT = Path(__file__).resolve().parents[1]
STATE = ("DOMAIN_SEPARATOR", "SEED", "GAMMA_NUM", "GAMMA_DEN", "MIN_EFFECTIVE_TOKENS", "THRESHOLD_NUM", "THRESHOLD_DEN")


def synthetic_text(count: int) -> str:
    return " ".join("token" + chr(97 + index // 26) + chr(97 + index % 26) for index in range(count))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(protocol.encoded(value))


def review_template(root: Path, sounds: dict | None = None) -> None:
    template = root / "fixtures/template-v3.json"
    write_json(root / "fixtures/candidate-review-v3.json", {
        "schema": candidate_review.SCHEMA,
        "method": candidate_review.METHOD,
        "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
        "article_sounds": sounds or {},
        "entries": [{**variant, "grammar_approved": True, "same_job_approved": True, "rationale": "Synthetic predicate adjective with the same instruction."} for variant in candidate_review.render_variants(template)],
    })


class ReviewTests(unittest.TestCase):
    def test_every_article_follower_is_reviewed_including_digits_and_quotes(self) -> None:
        for follower in ("11-month", '"additional"', "(empty)", "[empty]", "unknown"):
            with self.subTest(follower=follower), self.assertRaisesRegex(ValueError, "unreviewed article follower"):
                candidate_review._validate_articles("a " + follower + " check", {})
        candidate_review._validate_articles("an 11-month check", {"11-month": "vowel"})
        with self.assertRaisesRegex(ValueError, "agreement mismatch"):
            candidate_review._validate_articles("a 11-month check", {"11-month": "vowel"})

    def test_variable_slots_after_articles_are_rejected(self) -> None:
        for prefix in ("A ", "an ", 'a "', "a ("):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "template.json"
                write_json(path, {"segments": [prefix, ["small", "minor"], " error."]})
                with self.assertRaisesRegex(ValueError, "follows an indefinite article"):
                    candidate_review.render_variants(path)

    def test_variable_article_choice_cannot_precede_another_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.json"
            write_json(path, {"segments": ["Use ", ["the", "a"], " ", ["small", "minor"], " error."]})
            with self.assertRaisesRegex(ValueError, "follows an indefinite article"):
                candidate_review.render_variants(path)

    def test_each_variant_includes_following_sentences_in_its_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.json"
            write_json(path, {"segments": ["Use the ", ["band", "range"], ". The band defines the limit.\n\nKeep this separate."]})
            variants = candidate_review.render_variants(path)
            self.assertEqual(variants[1]["paragraph"], "Use the range. The band defines the limit.")
            self.assertNotIn("separate", variants[1]["paragraph"])

    def test_review_requires_the_exact_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "fixtures/template-v3.json", {"segments": ["Use the ", ["band", "range"], ". The band defines the limit."]})
            review_template(root)
            path = root / "fixtures/candidate-review-v3.json"
            review = json.loads(path.read_bytes())
            review["entries"][1]["paragraph"] = "Use the range."
            write_json(path, review)
            with self.assertRaisesRegex(ValueError, "paragraph differs"):
                candidate_review.validate(root / "fixtures/template-v3.json", path)

    def test_reviewed_template_uses_literal_articles_and_consistent_band(self) -> None:
        template = json.loads((ROOT / "fixtures/template-v3.json").read_bytes())
        self.assertEqual(template["segments"][31], "small")
        self.assertEqual(template["segments"][57], "band")
        candidate_review.validate(ROOT / "fixtures/template-v3.json", ROOT / "fixtures/candidate-review-v3.json")
        self.assertGreaterEqual(protocol.literal_pair_bound(template["segments"]), 201)


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {name: getattr(declawd, name) for name in STATE}
        self.addCleanup(lambda: [setattr(declawd, name, value) for name, value in self.state.items()])
        self.profile = {"profile_id": "declawd-v3", "domain_separator": "declawd/v3/green", "seed_hex": "11" * 32, "gamma": {"numerator": 1, "denominator": 4}, "threshold": {"numerator": 200, "denominator": 100}, "min_effective_tokens": 200, "tokeniser_pattern": declawd.TOKEN_PATTERN.pattern}

    def load(self, profile: dict) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            write_json(path, profile)
            declawd.load_profile(path)

    def test_invalid_profile_preserves_every_global(self) -> None:
        mutations = [
            lambda p: p["threshold"].update(denominator=0),
            lambda p: p["threshold"].update(denominator=-1),
            lambda p: p.pop("domain_separator"),
            lambda p: p.update(domain_separator="declawd/v1/green"),
            lambda p: p.update(seed_hex="ff"),
            lambda p: p["gamma"].update(numerator=0),
            lambda p: p["gamma"].update(numerator=2, denominator=8),
            lambda p: p.update(min_effective_tokens=True),
            lambda p: p.update(tokeniser_pattern="other"),
        ]
        for mutation in mutations:
            profile = copy.deepcopy(self.profile)
            mutation(profile)
            with self.subTest(profile=profile), self.assertRaises(declawd.DeclawdError):
                self.load(profile)
            self.assertEqual({name: getattr(declawd, name) for name in STATE}, self.state)

    def test_negative_denominator_has_its_own_error(self) -> None:
        self.profile["threshold"]["denominator"] = -2
        with self.assertRaisesRegex(declawd.DeclawdError, "threshold denominator"):
            self.load(self.profile)

    def test_profile_id_derives_domains_for_old_and_future_profiles(self) -> None:
        for profile_id in ("declawd-v1", "declawd-v2", "declawd-v2-r2", "declawd-v3", "declawd-v123"):
            self.assertEqual(declawd.domain_for_profile(profile_id), ("declawd/" + profile_id[8:] + "/green").encode())
        self.load(self.profile)
        self.assertEqual((declawd.THRESHOLD_NUM, declawd.THRESHOLD_DEN), (2, 1))


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        isolated = mock.patch.dict(os.environ, environment, clear=True)
        isolated.start()
        self.addCleanup(isolated.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.root = self.repo / "experiments/declawd-v3"
        for name in protocol.INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        write_json(self.root / "fixtures/template-v3.json", {"fixture_id": "synthetic-v3", "segments": [synthetic_text(210) + ". The result is ", ["plain", "simple"], "."]})
        review_template(self.root)
        write_json(self.root / "fixtures/corpus.json", {"passages": [
            {"id": "cal", "author": "calibration-author", "split": "calibration", "text": synthetic_text(220)},
            {"id": "eval", "author": "evaluation-author", "split": "evaluation", "text": synthetic_text(220)},
        ]})
        state = mock.patch.multiple(declawd, **{name: getattr(declawd, name) for name in STATE})
        state.start()
        self.addCleanup(state.stop)
        self.git("init", "--quiet")
        self.commit()

    def git(self, *arguments: str) -> str:
        return subprocess.check_output(["git", "-c", "user.name=Protocol Test", "-c", "user.email=protocol@example.invalid", "-c", "maintenance.auto=false", "-c", "gc.auto=0", *arguments], cwd=self.repo, text=True, stderr=subprocess.STDOUT).strip()

    def commit(self) -> None:
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "--no-verify", "--quiet", "-m", "freeze synthetic inputs")

    def registered(self) -> None:
        protocol.register(self.root)
        self.commit()

    def seeded(self) -> None:
        self.registered()
        with mock.patch.object(protocol.secrets, "token_bytes", return_value=b"\x11" * 32) as draw:
            protocol.sample(self.root)
            draw.assert_called_once_with(32)
        self.assertFalse(any((self.root / name).exists() for name in protocol.OUTPUTS))
        self.commit()

    def complete(self) -> dict[str, bytes]:
        self.seeded()
        protocol.reproduce(self.root, write=True)
        return {name: (self.root / name).read_bytes() for name in protocol.OUTPUTS}

    def test_nested_root_checks_the_actual_committed_paths(self) -> None:
        protocol.register(self.root)
        self.assertTrue((self.root / protocol.REGISTRATION).exists())

    def test_changed_registered_bytes_are_rejected(self) -> None:
        (self.root / "fixtures/rewrite.json").write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "commit the registered bytes"):
            protocol.register(self.root)

    def test_staged_nested_file_is_rejected(self) -> None:
        path = self.root / "fixtures/rewrite.json"
        before = path.read_bytes()
        path.write_bytes(b"changed\n")
        self.git("add", ".")
        path.write_bytes(before)
        with self.assertRaisesRegex(ValueError, "staged changes"):
            protocol.register(self.root)

    def test_fixture_id_is_checked_before_sampling(self) -> None:
        path = self.root / "fixtures/template-v3.json"
        template = json.loads(path.read_bytes())
        template.pop("fixture_id")
        write_json(path, template)
        review_template(self.root)
        with mock.patch.object(protocol.secrets, "token_bytes") as draw:
            with self.assertRaisesRegex(ValueError, "fixture_id"):
                protocol.register(self.root)
        draw.assert_not_called()
        self.assertFalse((self.root / protocol.SEED).exists())

    def test_marked_minimum_is_guaranteed_before_sampling(self) -> None:
        write_json(self.root / "fixtures/template-v3.json", {"fixture_id": "short", "segments": [synthetic_text(197) + ". The result is ", ["plain", "simple"], "."]})
        review_template(self.root)
        with mock.patch.object(protocol.secrets, "token_bytes") as draw:
            with self.assertRaisesRegex(ValueError, "immutable literal pairs"):
                protocol.register(self.root)
        draw.assert_not_called()

    def test_uncommitted_registration_prevents_a_draw(self) -> None:
        protocol.register(self.root)
        with mock.patch.object(protocol.secrets, "token_bytes") as draw:
            with self.assertRaises(subprocess.CalledProcessError):
                protocol.sample(self.root)
        draw.assert_not_called()

    def test_one_draw_is_separate_from_scoring_and_requires_seed_commit(self) -> None:
        self.registered()
        with mock.patch.object(protocol.secrets, "token_bytes", return_value=b"\x11" * 32) as draw, mock.patch.object(declawd, "score") as score:
            protocol.sample(self.root)
            with self.assertRaisesRegex(ValueError, "seed or output already exists"):
                protocol.sample(self.root)
            with self.assertRaises(subprocess.CalledProcessError):
                protocol.reproduce(self.root, write=True)
        draw.assert_called_once_with(32)
        score.assert_not_called()

    def test_all_surviving_outputs_block_seed_changes_without_calibration(self) -> None:
        complete = self.complete()
        seed = json.loads((self.root / protocol.SEED).read_bytes())
        seed["seed_hex"] = "22" * 32
        write_json(self.root / protocol.SEED, seed)
        for survivor in protocol.OUTPUTS:
            with self.subTest(survivor=survivor):
                for name in protocol.OUTPUTS:
                    (self.root / name).unlink(missing_ok=True)
                (self.root / survivor).write_bytes(complete[survivor])
                before = (self.root / survivor).read_bytes()
                with mock.patch.object(declawd, "score") as score, mock.patch.object(protocol, "atomic_write") as write:
                    with self.assertRaisesRegex(ValueError, "existing output"):
                        protocol.reproduce(self.root, write=True)
                score.assert_not_called()
                write.assert_not_called()
                self.assertEqual((self.root / survivor).read_bytes(), before)

    def test_interrupted_atomic_replace_leaves_a_complete_old_file(self) -> None:
        complete = self.complete()
        name = protocol.OUTPUTS[0]
        with mock.patch.object(protocol.os, "replace", side_effect=OSError("interrupted replacement")):
            with self.assertRaisesRegex(OSError, "interrupted replacement"):
                protocol.atomic_write(self.root, name, {"changed": True}, replace=True)
        self.assertEqual((self.root / name).read_bytes(), complete[name])
        self.assertFalse(list((self.root / name).parent.glob("." + Path(name).name + "-*")))

    def test_interrupted_publication_does_not_create_a_partial_seed(self) -> None:
        with mock.patch.object(protocol.os, "link", side_effect=OSError("interrupted publication")):
            with self.assertRaisesRegex(OSError, "interrupted publication"):
                protocol.exclusive(self.root, protocol.SEED, {"seed_hex": "11" * 32})
        self.assertFalse((self.root / protocol.SEED).exists())

    def test_partial_output_set_can_be_repaired_and_reproduced(self) -> None:
        complete = self.complete()
        for name in protocol.OUTPUTS[1:]:
            (self.root / name).unlink()
        protocol.reproduce(self.root, write=True)
        self.assertEqual({name: (self.root / name).read_bytes() for name in protocol.OUTPUTS}, complete)
        with mock.patch.object(protocol.secrets, "token_bytes") as draw:
            protocol.reproduce(self.root)
        draw.assert_not_called()

    def test_threshold_is_frozen_before_evaluation_is_scored(self) -> None:
        self.seeded()
        events = []
        original_cohort, original_threshold = protocol.cohort_rows, protocol.choose_threshold
        def cohort(passages: list[dict]) -> dict:
            events.append(passages[0]["split"])
            return original_cohort(passages)
        def threshold(groups: dict) -> int:
            events.append("threshold")
            return original_threshold(groups)
        with mock.patch.object(protocol, "cohort_rows", side_effect=cohort), mock.patch.object(protocol, "choose_threshold", side_effect=threshold):
            protocol.reproduce(self.root, write=True)
        self.assertEqual(events, ["calibration", "threshold", "evaluation"])


class HistoryTests(unittest.TestCase):
    setUp = ProtocolTests.setUp
    git = ProtocolTests.git
    commit = ProtocolTests.commit
    registered = ProtocolTests.registered
    seeded = ProtocolTests.seeded
    complete = ProtocolTests.complete
    def verifier(self):
        spec = importlib.util.spec_from_file_location("declawd_v3_history", ROOT / "verify.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_history_requires_outputs_after_seed_commit(self) -> None:
        self.complete()
        verifier = self.verifier()
        with self.assertRaisesRegex(ValueError, "no committed history"):
            verifier.verify_history(self.root)
        self.commit()
        result = verifier.verify_history(self.root)
        self.assertNotEqual(result["registration_commit"], result["seed_commit"])
        self.assertTrue(all(commit != result["seed_commit"] for commit in result["output_commits"].values()))

    def test_history_detects_seed_rewritten_after_its_first_commit(self) -> None:
        self.complete()
        self.commit()
        seed = json.loads((self.root / protocol.SEED).read_bytes())
        seed["sampled_at"] = "changed after recording"
        write_json(self.root / protocol.SEED, seed)
        self.commit()
        with self.assertRaisesRegex(ValueError, "seed changed"):
            self.verifier().verify_history(self.root)


class ArchiveTests(unittest.TestCase):
    def test_archived_r2_payload_has_exact_hashes_and_reproduces(self) -> None:
        archive = ROOT.parent / "declawd-v2-r2"
        manifest = json.loads((archive / "archive-manifest.json").read_bytes())
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((archive / name).read_bytes()).hexdigest(), digest, name)
        subprocess.run([os.sys.executable, str(archive / "reference/calibrate_v2.py"), "reproduce"], cwd=ROOT.parents[1], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
