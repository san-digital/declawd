from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

import calibrate_v2
import declawd


def synthetic_text(count: int) -> str:
    return " ".join(
        "token" + chr(97 + index // 26) + chr(97 + index % 26)
        for index in range(count)
    )


class LengthBoundaryTests(unittest.TestCase):
    def test_prefixes_have_exact_pair_counts(self) -> None:
        text = synthetic_text(240)
        for count in (199, 200, 201):
            with self.subTest(pairs=count):
                prefix = calibrate_v2.prefix_at_pairs(text, count)
                self.assertIsNotNone(prefix)
                self.assertTrue(text.startswith(prefix))
                self.assertEqual(declawd.count_contexts(prefix), count)
                tokens = list(declawd.TOKEN_PATTERN.finditer(prefix))
                self.assertEqual(declawd.count_contexts(prefix[:tokens[-1].start()]), count - 1)

    def test_prefixes_count_distinct_pairs_and_keep_delimiters(self) -> None:
        text = "ALFA, alfa! alfa? beta... beta gamma"
        prefix = calibrate_v2.prefix_at_pairs(text, 4)
        self.assertEqual(prefix, "ALFA, alfa! alfa? beta... beta")
        self.assertEqual(declawd.count_contexts(prefix), 4)
        self.assertIsNone(calibrate_v2.prefix_at_pairs(text, 6))

    def test_public_score_hides_counts_and_z_below_200(self) -> None:
        with mock.patch.multiple(
            declawd,
            SEED=b"\x11" * 32,
            GAMMA_NUM=1,
            GAMMA_DEN=4,
            MIN_EFFECTIVE_TOKENS=200,
            THRESHOLD_NUM=200,
            THRESHOLD_DEN=100,
        ):
            for count in (199, 200, 201):
                with self.subTest(pairs=count):
                    result = calibrate_v2.score_record(synthetic_text(count))
                    self.assertEqual(result["effective"], count)
                    if count < 200:
                        self.assertEqual(result["verdict"], "insufficient text")
                        self.assertIsNone(result["green"])
                        self.assertIsNone(result["z"])
                    else:
                        self.assertIsInstance(result["green"], int)
                        self.assertIsInstance(result["z"], float)
                        self.assertIn(result["verdict"], {"above threshold", "below threshold"})


class ThresholdTests(unittest.TestCase):
    @staticmethod
    def group(*greens: int) -> list[dict]:
        return [
            {"effective_tokens": 300, "green": green}
            for green in [*greens, *([75] * (50 - len(greens)))]
        ]

    def test_strict_comparison_accepts_exact_threshold(self) -> None:
        threshold = calibrate_v2.choose_threshold({
            name: self.group(90, 90, 105) for name in calibrate_v2.CALIBRATION_GROUPS
        })
        self.assertEqual(threshold, 200)

    def test_every_eligible_length_group_meets_the_target(self) -> None:
        threshold = calibrate_v2.choose_threshold({
            "prefix_200": self.group(90, 90, 105),
            "prefix_201": self.group(100, 100),
            "full": self.group(75),
        })
        self.assertEqual(threshold, 335)

    def test_empty_calibration_group_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "every calibration length group"):
            calibrate_v2.choose_threshold({
                "prefix_200": self.group(75),
                "prefix_201": [],
                "full": self.group(75),
            })


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in calibrate_v2.INPUTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes() if name.startswith("reference/") else b"{}\n")
        (self.root / "fixtures/perturbations.json").write_text(
            json.dumps({"targets": {}}), encoding="utf-8"
        )
        template_path = self.root / "fixtures/template-v2.json"
        template_path.write_text(json.dumps({"fixture_id": "synthetic-v2", "segments": [
            synthetic_text(210) + ". The result is ", ["plain", "simple"], "."
        ]}), encoding="utf-8")
        (self.root / "fixtures/candidate-review-v2.json").write_text(json.dumps({
            "schema": calibrate_v2.candidate_review.SCHEMA,
            "method": calibrate_v2.candidate_review.METHOD,
            "template_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
            "entries": [{
                **variant,
                "grammar_approved": True,
                "same_job_approved": True,
                "rationale": "Synthetic test sentence with a predicate adjective.",
            } for variant in calibrate_v2.candidate_review.render_variants(template_path)],
        }), encoding="utf-8")
        (self.root / "fixtures/corpus.json").write_text(json.dumps({"passages": [
            {"id": "cal", "author": "author-a", "split": "calibration", "text": synthetic_text(220)},
            {"id": "eval", "author": "author-b", "split": "evaluation", "text": synthetic_text(220)},
        ]}), encoding="utf-8")
        self.git("init", "--quiet")
        self.commit()

    def git(self, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "user.name=Protocol Test", "-c", "user.email=protocol@example.invalid", *arguments],
            cwd=self.root,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()

    def commit(self) -> None:
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "freeze synthetic inputs")

    def registered(self) -> None:
        calibrate_v2.register(self.root)
        self.commit()

    def test_register_requires_committed_input_bytes(self) -> None:
        (self.root / "fixtures/rewrite.json").write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "commit the registered bytes"):
            calibrate_v2.register(self.root)
        self.assertFalse((self.root / calibrate_v2.REGISTRATION).exists())

    def test_register_cannot_replace_an_existing_registration(self) -> None:
        calibrate_v2.register(self.root)
        before = (self.root / calibrate_v2.REGISTRATION).read_bytes()
        with self.assertRaises(FileExistsError):
            calibrate_v2.register(self.root)
        self.assertEqual((self.root / calibrate_v2.REGISTRATION).read_bytes(), before)

    def test_sample_requires_registration_to_be_committed(self) -> None:
        calibrate_v2.register(self.root)
        with mock.patch.object(calibrate_v2.secrets, "token_bytes") as draw:
            with self.assertRaises(subprocess.CalledProcessError):
                calibrate_v2.sample(self.root)
        draw.assert_not_called()
        self.assertFalse((self.root / calibrate_v2.SEED).exists())

    def test_changed_input_is_rejected_before_drawing(self) -> None:
        self.registered()
        (self.root / "fixtures/rewrite.json").write_bytes(b"changed\n")
        with mock.patch.object(calibrate_v2.secrets, "token_bytes") as draw:
            with self.assertRaisesRegex(ValueError, "registered inputs or procedure changed"):
                calibrate_v2.sample(self.root)
        draw.assert_not_called()

    def test_seed_is_recorded_before_scoring_and_survives_a_failure(self) -> None:
        self.registered()

        def failed_run(root: Path, write: bool) -> None:
            self.assertTrue(write)
            seed = json.loads((root / calibrate_v2.SEED).read_bytes())
            self.assertEqual(seed["seed_hex"], "11" * 32)
            self.assertEqual(seed["registration_commit"], self.git("rev-parse", "HEAD"))
            raise RuntimeError("synthetic scoring failure")

        with mock.patch.object(calibrate_v2.secrets, "token_bytes", return_value=b"\x11" * 32) as draw:
            with mock.patch.object(calibrate_v2, "reproduce", side_effect=failed_run):
                with self.assertRaisesRegex(RuntimeError, "synthetic scoring failure"):
                    calibrate_v2.sample(self.root)
            with self.assertRaisesRegex(ValueError, "seed or output already exists"):
                calibrate_v2.sample(self.root)
        draw.assert_called_once_with(32)

    def test_existing_outputs_prevent_another_draw(self) -> None:
        self.registered()
        (self.root / calibrate_v2.OUTPUTS[0]).write_bytes(b"{}\n")
        with mock.patch.object(calibrate_v2.secrets, "token_bytes") as draw:
            with self.assertRaisesRegex(ValueError, "seed or output already exists"):
                calibrate_v2.sample(self.root)
        draw.assert_not_called()

    def test_mismatched_seed_registration_is_rejected_before_scoring(self) -> None:
        self.registered()
        (self.root / calibrate_v2.SEED).write_text(json.dumps({
            "registration_sha256": "00" * 32,
            "seed_hex": "11" * 32,
        }), encoding="utf-8")
        with mock.patch.object(declawd, "score") as score:
            with self.assertRaisesRegex(ValueError, "seed is not bound to this registration"):
                calibrate_v2.reproduce(self.root)
        score.assert_not_called()

    def test_full_synthetic_run_reproduces_without_writing_or_drawing(self) -> None:
        self.registered()
        names = (
            "SEED", "GAMMA_NUM", "GAMMA_DEN", "THRESHOLD_NUM", "THRESHOLD_DEN",
            "MIN_EFFECTIVE_TOKENS", "DOMAIN_SEPARATOR",
        )
        events = []
        cohort_rows = calibrate_v2.cohort_rows
        choose_threshold = calibrate_v2.choose_threshold

        def record_cohort(passages: list[dict]) -> dict:
            events.append(passages[0]["split"])
            return cohort_rows(passages)

        def record_threshold(groups: dict) -> int:
            events.append("threshold")
            return choose_threshold(groups)

        with mock.patch.multiple(declawd, **{name: getattr(declawd, name) for name in names}):
            with mock.patch.object(calibrate_v2.secrets, "token_bytes", return_value=b"\x11" * 32) as draw:
                with mock.patch.object(calibrate_v2, "cohort_rows", side_effect=record_cohort):
                    with mock.patch.object(calibrate_v2, "choose_threshold", side_effect=record_threshold):
                        calibrate_v2.sample(self.root)
                        recorded = {
                            name: (self.root / name).read_bytes()
                            for name in (*calibrate_v2.INPUTS, calibrate_v2.REGISTRATION, calibrate_v2.SEED, *calibrate_v2.OUTPUTS)
                        }
                        reports = calibrate_v2.reproduce(self.root)
                draw.assert_called_once_with(32)
            self.assertEqual(events, ["calibration", "threshold", "evaluation"] * 2)
            for name, content in recorded.items():
                self.assertEqual((self.root / name).read_bytes(), content)
            evaluation = reports["reports/evaluation-report-v2.json"]
            short = evaluation["length_groups"]["prefix_199"]
            self.assertIsNone(short["rate"])
            self.assertEqual(short["usable"], 0)
            self.assertIsNone(short["rows"][0]["green"])
            self.assertIsNone(short["rows"][0]["z"])
            self.assertIsNone(short["rows"][0]["crossed"])
            changed = self.root / "vectors/scoring-v2.json"
            changed.write_bytes(b"{}\n")
            with self.assertRaisesRegex(ValueError, "reproduction differs"):
                calibrate_v2.reproduce(self.root)
            self.assertEqual(changed.read_bytes(), b"{}\n")

    def test_recorded_seed_edit_is_rejected_before_scoring(self) -> None:
        self.registered()
        names = (
            "SEED", "GAMMA_NUM", "GAMMA_DEN", "THRESHOLD_NUM", "THRESHOLD_DEN",
            "MIN_EFFECTIVE_TOKENS", "DOMAIN_SEPARATOR",
        )
        with mock.patch.multiple(declawd, **{name: getattr(declawd, name) for name in names}):
            with mock.patch.object(calibrate_v2.secrets, "token_bytes", return_value=b"\x11" * 32):
                calibrate_v2.sample(self.root)
            seed = json.loads((self.root / calibrate_v2.SEED).read_bytes())
            seed["seed_hex"] = "22" * 32
            (self.root / calibrate_v2.SEED).write_bytes(calibrate_v2.encoded(seed))
            with mock.patch.object(declawd, "score") as score:
                with self.assertRaisesRegex(ValueError, "seed"):
                    calibrate_v2.reproduce(self.root, write=True)
            score.assert_not_called()


class ProfileTests(unittest.TestCase):
    def test_rational_threshold_is_not_treated_as_a_whole_number(self) -> None:
        profile = {
            "profile_id": "declawd-v2",
            "seed_hex": "11" * 32,
            "gamma": {"numerator": 1, "denominator": 4},
            "threshold": {"numerator": 200, "denominator": 100},
            "min_effective_tokens": 200,
            "domain_separator": "declawd/v1/green",
            "tokeniser_pattern": declawd.TOKEN_PATTERN.pattern,
        }
        names = (
            "SEED", "GAMMA_NUM", "GAMMA_DEN", "THRESHOLD_NUM", "THRESHOLD_DEN",
            "MIN_EFFECTIVE_TOKENS", "DOMAIN_SEPARATOR",
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.multiple(
            declawd, **{name: getattr(declawd, name) for name in names}
        ):
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            declawd.load_profile(path)
            self.assertEqual(declawd.THRESHOLD_NUM / declawd.THRESHOLD_DEN, 2)
            self.assertEqual(declawd.verdict(300, 90), "below threshold")
            self.assertEqual(declawd.verdict(300, 91), "above threshold")


class FrozenV1BytesTests(unittest.TestCase):
    def test_v1_fixture_report_and_vector_bytes_are_preserved(self) -> None:
        expected = {
            "fixtures/template.json": "9b84e2d6325188017017d07fdfed50b74515931093771f823492c34b23fc4316",
            "fixtures/corpus.json": "a130254999663f085c1efb317c4ef5fbc5d25e2d7cb9c2ea10c407f3b9241339",
            "fixtures/rewrite.json": "e5e672b4d230f9153f9da0a8251b64fda9b08fd26333b30ef5884a5fcf41bc7d",
            "fixtures/perturbations.json": "20504d1dd3a46adb58fc39763a750c48425fee065d95084a227cbb017ebbf8e2",
            "fixtures/profile-v1.json": "4dde7f057b7d29a8846cd75043321126f92c1662a90d8a039d2696b6b28fba39",
            "fixtures/registration-v1.json": "82dfb1128450d73970e812637a7be307901d7cdd66b53660c6eef83cb8e63d97",
            "reports/calibration-report-v1.json": "702a3a98677ed98c2f41b020305e52d49771698610657a9b204057cc4be72d4a",
            "reports/evaluation-report-v1.json": "926fcb9c5351a504e225f8d1208b8833909550c0e086564677e62856ac399cfc",
            "vectors/scoring-v1.json": "239532206448f41e04a136949e2b23391c764c0d9e60dfc5ae06af54bda09456",
            "vectors/controlled-removal-v1.json": "5b3c2bd2d477479a73c182b30a2db228a4a7b6a3e435eff28679d5d085dbfc73",
        }
        for name, digest in expected.items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
