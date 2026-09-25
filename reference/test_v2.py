from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import re
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


class PublishedV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        names = (
            "SEED", "GAMMA_NUM", "GAMMA_DEN", "THRESHOLD_NUM", "THRESHOLD_DEN",
            "MIN_EFFECTIVE_TOKENS", "DOMAIN_SEPARATOR",
        )
        state = mock.patch.multiple(declawd, **{name: getattr(declawd, name) for name in names})
        state.start()
        self.addCleanup(state.stop)
        declawd.load_profile(ROOT / "fixtures/profile-v2.json")

    @staticmethod
    def read(name: str) -> dict:
        return json.loads((ROOT / name).read_bytes())

    def assert_score(self, text: str, expected: dict) -> None:
        score = declawd.score(text)
        self.assertEqual(score.raw_tokens, expected["raw"])
        self.assertEqual(score.effective_tokens, expected["effective"])
        self.assertEqual(score.verdict, expected["verdict"])
        if score.effective_tokens < 200:
            self.assertIsNone(expected["green"])
            self.assertIsNone(expected["z"])
        else:
            self.assertEqual(score.green, expected["green"])
            self.assertAlmostEqual(score.z_display, expected["z"], places=14)

    def test_profile_seed_registration_and_reports_bind_exact_bytes(self) -> None:
        profile = self.read("fixtures/profile-v2.json")
        seed = self.read("fixtures/seed-v2.json")
        registration = self.read("fixtures/registration-v2.json")
        calibration = self.read("reports/calibration-report-v2.json")
        evaluation = self.read("reports/evaluation-report-v2.json")
        self.assertEqual(profile["profile_id"], "declawd-v2-r2")
        self.assertEqual(profile["domain_separator"], "declawd/v2-r2/green")
        self.assertEqual(profile["min_effective_tokens"], 200)
        self.assertEqual(profile["threshold"]["denominator"], 1)
        self.assertEqual(profile["threshold"]["numerator"], calibration["threshold"])
        self.assertNotEqual(seed["registration_commit"], "d87977b989555f40da623675fd8053df8d120e1d")
        self.assertNotEqual(seed["seed_hex"], "be14186bfb7b4e2261e3ae1a493816bf92320a0a0fb39f4f02e0485e9bf45c98")
        self.assertEqual(profile["seed_hex"], seed["seed_hex"])
        self.assertEqual(calibration["seed_hex"], seed["seed_hex"])
        for name, expected in registration["source_files"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
        for source, records, field in (
            ("fixtures/registration-v2.json", [seed, profile, calibration], "registration_sha256"),
            ("fixtures/seed-v2.json", [calibration], "seed_record_sha256"),
            ("reports/calibration-report-v2.json", [profile], "calibration_report_sha256"),
            ("fixtures/profile-v2.json", [evaluation], "profile_sha256"),
        ):
            expected = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
            for record in records:
                self.assertEqual(record[field], expected)

    def test_published_scoring_vectors_match_the_profile(self) -> None:
        document = self.read("vectors/scoring-v2.json")
        self.assertEqual(document["profile"], self.read("fixtures/profile-v2.json"))
        for index, vector in enumerate(document["vectors"]):
            with self.subTest(vector=index):
                self.assert_score(vector["text"], vector)
        self.assertTrue({199, 200, 201} <= {v["effective"] for v in document["vectors"]})

    def test_length_reports_retain_every_result_and_mask_199_pairs(self) -> None:
        expected = {
            "calibration": {"prefix_200": 96, "prefix_201": 95, "full": 96},
            "evaluation": {"prefix_200": 96, "prefix_201": 94, "full": 96},
        }
        for split, counts in expected.items():
            report = self.read(f"reports/{split}-report-v2.json")
            self.assertEqual(report["threshold"], self.read("fixtures/profile-v2.json")["threshold"]["numerator"])
            short = report["length_groups"]["prefix_199"]
            self.assertEqual((short["source_passages"], short["passages"], short["below_minimum"]), (96, 96, 96))
            self.assertEqual(short["usable"], 0)
            self.assertIsNone(short["rate"])
            self.assertIsNone(short["wilson_95"])
            self.assertEqual(short["scores"], [])
            for row in short["rows"]:
                self.assertEqual(row["effective_tokens"], 199)
                self.assertEqual(row["verdict"], "insufficient text")
                for field in ("green", "z", "crossed"):
                    self.assertIsNone(row[field])
            for name, total in counts.items():
                group = report["length_groups"][name]
                crossings = group["crossings"]
                self.assertEqual(group["usable"], total)
                self.assertEqual(group["passages"] + group["unavailable"], 96)
                self.assertEqual(len(group["rows"]), total)
                self.assertEqual(group["rate"], round(crossings / total, 4))
                crossed = [row["id"] for row in group["rows"] if row["crossed"]]
                self.assertEqual(crossed, group["crossing_ids"])
                self.assertEqual(len(crossed), crossings)
                for row in group["rows"]:
                    self.assertEqual(
                        row["crossed"],
                        declawd.verdict(row["effective_tokens"], row["green"]) == "above threshold",
                    )
        calibration = self.read("reports/calibration-report-v2.json")
        segments = self.read("fixtures/template-v2.json")["segments"]
        for name, marked in (("marked_fixture", True), ("control_fixture", False)):
            score = declawd.score(declawd.generate(segments, marked=marked))
            expected = {"effective_tokens": score.effective_tokens, "z": round(score.z_display, 2)}
            if marked:
                expected["detected"] = score.verdict == "above threshold"
            self.assertEqual(calibration[name], expected)

    def test_threshold_is_the_first_grid_value_meeting_every_calibration_group(self) -> None:
        report = self.read("reports/calibration-report-v2.json")
        groups = report["length_groups"]
        eligible = [groups[name] for name in ("prefix_200", "prefix_201", "full")]
        self.assertTrue(all(group["crossings"] * 50 <= group["usable"] for group in eligible))
        numerator = round(report["threshold"] * 100)
        self.assertEqual(numerator % 5, 0)
        if numerator == 0:
            return
        with mock.patch.multiple(declawd, THRESHOLD_NUM=numerator - 5, THRESHOLD_DEN=100):
            previous = [
                sum(declawd.verdict(row["effective_tokens"], row["green"]) == "above threshold" for row in group["rows"])
                for group in eligible
            ]
        self.assertTrue(any(crossings * 50 > group["usable"] for crossings, group in zip(previous, eligible)))

    def test_controlled_removal_uses_reviewed_alternatives_and_original_offsets(self) -> None:
        document = self.read("vectors/controlled-removal-v2.json")
        template = self.read("fixtures/template-v2.json")
        self.assertEqual(document["fixture_id"], template["fixture_id"])
        self.assertEqual(document["profile_id"], "declawd-v2-r2")
        self.assertEqual(document["source_text"], declawd.generate(template["segments"], marked=True))
        self.assert_score(document["source_text"], document["source_score"])
        slots = {}
        offset = 0
        for part in template["segments"]:
            if isinstance(part, str):
                offset += len(part)
            else:
                before = declawd.TOKEN_PATTERN.match(document["source_text"], offset).group()
                slots[offset] = (before, part)
                offset += len(before)
        self.assertLessEqual(len(document["steps"]), 6)
        previous = document["source_score"]["z"]
        text = document["source_text"]
        for count, step in enumerate(document["steps"], start=1):
            self.assertEqual(step["applied"], count)
            self.assertEqual(step["substitution"], document["substitutions"][count - 1])
            text = document["source_text"]
            for change in sorted(document["substitutions"][:count], key=lambda c: c["scalar_offset"], reverse=True):
                offset = change["scalar_offset"]
                before, candidates = slots[offset]
                self.assertEqual(change["before"], before)
                self.assertIn(change["after"], candidates)
                self.assertEqual(text[offset:offset + len(before)], before)
                text = text[:offset] + change["after"] + text[offset + len(before):]
            self.assert_score(text, step["score"])
            self.assertLess(step["score"]["z"], previous)
            previous = step["score"]["z"]
        self.assertEqual(text, document["expected_text"])
        self.assert_score(text, document["expected_score"])

    def test_recorded_run_reproduces_every_output_without_sampling(self) -> None:
        before = {name: (ROOT / name).read_bytes() for name in (calibrate_v2.SEED, *calibrate_v2.OUTPUTS)}
        with mock.patch.object(calibrate_v2.secrets, "token_bytes") as draw:
            calibrate_v2.reproduce(ROOT)
        draw.assert_not_called()
        self.assertEqual(before, {name: (ROOT / name).read_bytes() for name in before})


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


class ArchivedAttemptTests(unittest.TestCase):
    archive = ROOT / "experiments/declawd-v2-attempt-1"

    def test_archive_manifest_binds_every_payload_file(self) -> None:
        manifest = json.loads((self.archive / "archive-manifest.json").read_bytes())
        self.assertEqual(manifest["source_commit"], "77c1d6e9dfad7018491308e13ddd5a4a1b9d08e0")
        self.assertEqual(len(manifest["files"]), 18)
        for name, expected in manifest["files"].items():
            self.assertEqual(hashlib.sha256((self.archive / name).read_bytes()).hexdigest(), expected)

    def test_original_seed_and_results_remain_visible(self) -> None:
        seed = json.loads((self.archive / "fixtures/seed-v2.json").read_bytes())
        profile = json.loads((self.archive / "fixtures/profile-v2.json").read_bytes())
        calibration = json.loads((self.archive / "reports/calibration-report-v2.json").read_bytes())
        evaluation = json.loads((self.archive / "reports/evaluation-report-v2.json").read_bytes())
        self.assertEqual(seed["registration_commit"], "d87977b989555f40da623675fd8053df8d120e1d")
        self.assertEqual(seed["seed_hex"], "be14186bfb7b4e2261e3ae1a493816bf92320a0a0fb39f4f02e0485e9bf45c98")
        self.assertEqual(profile["profile_id"], "declawd-v2")
        self.assertEqual(profile["threshold"], {"numerator": 1.65, "denominator": 1})
        self.assertEqual(calibration["marked_fixture"], {"detected": True, "effective_tokens": 377, "z": 2.94})
        self.assertEqual(calibration["control_fixture"], {"effective_tokens": 378, "z": 0.89})
        for group, expected in {"full": (2, 96), "prefix_200": (2, 96), "prefix_201": (2, 94)}.items():
            report = evaluation["length_groups"][group]
            self.assertEqual((report["crossings"], report["usable"]), expected)
        scoring = json.loads((self.archive / "vectors/scoring-v2.json").read_bytes())
        marked = scoring["vectors"][8]["text"]
        self.assertIn("a empty field", marked)
        self.assertIn("a additional check", marked)

    def test_current_validator_rejects_the_previously_approved_article_mismatch(self) -> None:
        review = json.loads((self.archive / "fixtures/candidate-review-v2.json").read_bytes())
        self.assertTrue(all(entry["grammar_approved"] and entry["same_job_approved"] for entry in review["entries"]))
        with self.assertRaisesRegex(ValueError, "article agreement mismatch"):
            calibrate_v2.candidate_review.validate(
                self.archive / "fixtures/template-v2.json",
                self.archive / "fixtures/candidate-review-v2.json",
            )

    def test_archived_source_and_outputs_reproduce_without_current_code(self) -> None:
        paths = [path for path in self.archive.rglob("*") if path.is_file()]
        before = {path: path.read_bytes() for path in paths}
        result = subprocess.run(
            [sys.executable, "-B", str(self.archive / "reference/calibrate_v2.py"), "reproduce"],
            cwd=self.archive,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("[ok] v2 reproduce", result.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in before})


class TemplateGrammarTests(unittest.TestCase):
    def test_article_sensitive_words_are_literal(self) -> None:
        template = json.loads((ROOT / "fixtures/template-v2.json").read_bytes())
        segments = template["segments"]
        candidates = {candidate.lower() for part in segments if isinstance(part, list) for candidate in part}
        self.assertNotIn("empty", candidates)
        self.assertNotIn("additional", candidates)
        control = "".join(part if isinstance(part, str) else part[0] for part in segments)
        self.assertIn("because a blank field tells the next reader nothing at all", control)
        self.assertIn("may need a further check before its next use", control)
        self.assertIn(" readings at 60 and 80 litres per minute", control)
        self.assertIn("preceding twelve-month", control)

    def test_all_sentence_combinations_keep_reviewed_article_agreement(self) -> None:
        segments = json.loads((ROOT / "fixtures/template-v2.json").read_bytes())["segments"]
        frames = [[]]
        for part in segments:
            if isinstance(part, list):
                frames[-1].append(part)
                continue
            for chunk in re.split(r"(?<=[.!?])(?=\s|$)", part):
                if chunk:
                    frames[-1].append([chunk])
                    if re.search(r"[.!?]\s*$", chunk):
                        frames.append([])
        followers = {"bad", "blank", "doubtful", "further", "gap", "later", "meter", "minor", "poor", "reference", "run", "signature", "slight", "small", "value"}
        combinations = 0
        for frame in (frame for frame in frames if frame):
            for parts in itertools.product(*frame):
                sentence = "".join(parts)
                combinations += 1
                self.assertNotRegex(sentence, r"\ba (?:empty|additional)\b")
                for article, word in re.findall(r"\b(a|an)\s+([A-Za-z]+)", sentence, re.IGNORECASE):
                    self.assertIn(word.lower(), followers, sentence)
                    self.assertEqual(article.lower(), "a", sentence)
        self.assertGreater(combinations, 115)


if __name__ == "__main__":
    unittest.main()
